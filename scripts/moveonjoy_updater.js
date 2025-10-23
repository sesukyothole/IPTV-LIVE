#!/usr/bin/env node
/**
 * MoveOnJoy Updater — Fast per-channel failover (no commenting)
 * - Place at scripts/moveonjoy_updater.js
 * - Playlist: PrimeVision/us.m3u (auto-detected)
 * - Only modifies moveonjoy.com URLs
 *
 * Behavior:
 * - Detect main flXX from playlist
 * - If a path is offline on main, find a working flNN for that path (balanced S2 search)
 * - Accept fallback only after stability checks (3 quick tries)
 * - Keep cached results within a run
 * - Write playlist and git commit/push only when changes occur
 */

const fs = require('fs');
const fsSync = require('fs');
const path = require('path');
const axios = require('axios');
const { spawnSync } = require('child_process');

const PLAYLIST_CANDIDATES = [
  path.join('PrimeVision', 'us.m3u'),
  path.join('IPTV-LIVE','PrimeVision','us.m3u'),
  path.join('gtvservices5','IPTV-LIVE','PrimeVision','us.m3u'),
  'us.m3u'
];

const SUB_MIN = 3;
const SUB_MAX = 50;
const SUB_RANGE = Array.from({length: SUB_MAX - SUB_MIN + 1}, (_, i) => `fl${SUB_MAX - i}`);
const RETRIES = 2;
const RETRY_DELAY = 500; // ms
const SAMPLE_LIMIT = 3; // sample channels per subdomain
const STABLE_TRIES = 3;
const STABLE_DELAY_MS = 700;
const MAX_ATTEMPTS = 8; // balanced S2 max alternatives per path
const WORKER_BATCH = 8; // parallel batch probing
const LAST_UPDATE_FILE = '.moveonjoy_last_update';
const COOLDOWN_SECONDS = 3600; // avoid frequent pushes, set 0 to disable

const HEAD_TIMEOUT = 3000;
const GET_TIMEOUT = 6000;
const SEGMENT_RANGE = 'bytes=0-65535'; // first ~64KB of segment

const FL_RE = /https?:\/\/(fl\d+)\.moveonjoy\.com\/([^\s]+)/i;

// simple in-run cache
const cache = new Map();

function log(...args){ console.log(new Date().toISOString(), ...args); }
function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

function find_playlist() {
  for (const p of PLAYLIST_CANDIDATES) {
    if (fsSync.existsSync(p)) {
      log('Found playlist at', p);
      return p;
    }
  }
  // fallback recursive search
  const results = (function walk(dir){
    const list = fsSync.readdirSync(dir, { withFileTypes: true });
    for (const e of list) {
      const p = path.join(dir, e.name);
      if (e.isFile() && e.name === 'us.m3u') return p;
      if (e.isDirectory()) {
        const r = walk(p);
        if (r) return r;
      }
    }
    return null;
  })('.');
  if (results) log('Found playlist via recursive search:', results);
  return results;
}

async function headRequest(url, timeout = HEAD_TIMEOUT) {
  try {
    return await axios.head(url, { timeout, maxRedirects: 5, validateStatus: null });
  } catch {
    return null;
  }
}

async function getBytes(url, timeout = GET_TIMEOUT, range = SEGMENT_RANGE) {
  try {
    return await axios.get(url, { timeout, responseType: 'arraybuffer', headers: { Range: range }, maxRedirects: 5, validateStatus: null });
  } catch {
    return null;
  }
}

// quick HEAD/short-GET check for m3u8 presence and minimal validation
async function fastCheckM3U(url) {
  if (cache.has(url)) return cache.get(url);
  // HEAD first
  const h = await headRequest(url);
  if (h && h.status >= 200 && h.status < 400) {
    const ct = (h.headers['content-type'] || '').toLowerCase();
    if (ct.includes('mpegurl') || ct.includes('vnd.apple.mpegurl')) {
      cache.set(url, true);
      return true;
    }
    // ambiguous -> short GET
    const g = await getBytes(url);
    if (g && g.status >= 200 && g.status < 400) {
      const text = Buffer.from(g.data).toString('utf8', 0, 5000);
      for (const L of text.split(/\r?\n/)) {
        const s = L.trim();
        if (!s || s.startsWith('#')) continue;
        if (s.endsWith('.ts') || s.endsWith('.m3u8')) {
          cache.set(url, true);
          return true;
        }
      }
    }
  }
  cache.set(url, false);
  return false;
}

// check segment content for video-like markers
function bufferHasVideoMarkers(buf) {
  if (!buf || buf.length < 16) return false;
  const arr = Buffer.from(buf);
  if (arr[0] === 0x47) return true; // MPEG-TS sync
  const patterns = [
    Buffer.from([0,0,0,1,0x67]),
    Buffer.from([0,0,0,1,0x65]),
    Buffer.from([0,0,0,1,0x40])
  ];
  for (const p of patterns) if (arr.includes(p)) return true;
  return false;
}

// deeper: parse playlist, fetch first segment bytes and check for video markers
async function checkStreamPlayable(url) {
  // quick playlist check
  if (!await fastCheckM3U(url)) return false;
  const g = await getBytes(url);
  if (!g || g.status >= 400) return false;
  let text;
  try { text = Buffer.from(g.data).toString('utf8'); } catch { return false; }
  for (const L of text.split(/\r?\n/)) {
    const s = L.trim();
    if (!s || s.startsWith('#')) continue;
    let segUrl;
    if (/^https?:\/\//i.test(s)) segUrl = s;
    else segUrl = url.replace(/\/[^\/]*$/, '') + '/' + s;
    // try HEAD first
    const h = await headRequest(segUrl);
    if (h && h.status >= 200 && h.status < 400) {
      const segGet = await getBytes(segUrl);
      if (segGet && segGet.status >= 200 && segGet.status < 400) {
        if (bufferHasVideoMarkers(segGet.data)) return true;
        else return false;
      }
    }
    break; // test only the first candidate
  }
  return false;
}

// stability: run fastCheckM3U multiple times and last try do checkStreamPlayable
async function ensureStable(url, tries = STABLE_TRIES, delay = STABLE_DELAY_MS) {
  for (let i = 1; i <= tries; i++) {
    const okFast = await fastCheckM3U(url);
    if (!okFast) {
      log(`Stability: fast check failed for ${url} (${i}/${tries})`);
      return false;
    }
    if (i === tries) {
      const okPlay = await checkStreamPlayable(url);
      if (!okPlay) {
        log(`Stability: deep playable check failed for ${url}`);
        return false;
      }
    }
    if (i < tries) await sleep(delay);
  }
  return true;
}

// parse playlist helpers
function readLines(p) { return fs.readFileSync(p, 'utf8').split(/\r?\n/); }
function writeLines(p, lines) { fs.writeFileSync(p, lines.join('\n') + '\n', 'utf8'); }

function extractFlFromUrl(url) {
  const m = FL_RE.exec(url);
  return m ? m[1] : null;
}
function extractPathFromUrl(url) {
  const m = FL_RE.exec(url);
  return m ? m[2] : null;
}
function replaceFlInUrl(url, newFl) {
  return url.replace(/fl\d+/, newFl);
}

// ranking store (simple file) — keeps success/fail counts per flNN during runs
const RANK_FILE = '.subdomain_health.json';
function loadRank(){ try { return JSON.parse(fs.readFileSync(RANK_FILE,'utf8')); } catch { return {}; } }
function saveRank(r){ try { fs.writeFileSync(RANK_FILE, JSON.stringify(r, null, 2),'utf8'); } catch{} }
function bumpRank(fl, ok){
  const r = loadRank();
  if (!r[fl]) r[fl] = {success:0,fail:0,last:0};
  if (ok) r[fl].success++; else r[fl].fail++;
  r[fl].last = Date.now();
  saveRank(r);
}
function rankedSubs() {
  const r = loadRank();
  const arr = [];
  for (let n = SUB_MAX; n >= SUB_MIN; n--) {
    const s = `fl${n}`;
    const data = r[s] || {success:0,fail:0,last:0};
    const rate = data.success + data.fail === 0 ? 0 : data.success / (data.success + data.fail);
    arr.push({ sub:s, rate, success:data.success, fail:data.fail, last:data.last });
  }
  arr.sort((a,b) => {
    if (b.rate !== a.rate) return b.rate - a.rate;
    if (b.success !== a.success) return b.success - a.success;
    return (b.last || 0) - (a.last || 0);
  });
  return arr.map(x => x.sub);
}

// Balanced S2 search list (use learned ranking first, limited attempts)
function buildBalancedSearchList(currentFl, maxAttempts = MAX_ATTEMPTS) {
  const ranked = rankedSubs();
  // return top maxAttempts from ranked excluding current
  const list = ranked.filter(s => s !== currentFl).slice(0, maxAttempts);
  return list;
}

// find a working subdomain for a given path using small parallel batches
async function findWorkingSubForPath(path, exclude = null, current = null, maxAttempts = MAX_ATTEMPTS) {
  const candidates = buildBalancedSearchList(current, maxAttempts);
  for (let i = 0; i < candidates.length; i += WORKER_BATCH) {
    const batch = candidates.slice(i, i + WORKER_BATCH);
    const promises = batch.map(async (fl) => {
      if (fl === exclude) return null;
      const url = `https://${fl}.moveonjoy.com/${path}`;
      try {
        const ok = await fastCheckM3U(url);
        if (!ok) { bumpRank(fl, false); return null; }
        if (await ensureStable(url)) {
          bumpRank(fl, true);
          return fl;
        } else {
          bumpRank(fl, false);
          return null;
        }
      } catch (e) {
        bumpRank(fl, false);
        return null;
      }
    });
    const results = await Promise.all(promises);
    for (const fl of results) if (fl) return fl;
  }
  return null;
}

// per-channel failover: test each MoveOnJoy line that references currentMain; if path fails on main -> find fallback & replace
async function perChannelFailover(lines, currentMain) {
  const newLines = lines.slice();
  let changed = false;
  // iterate lines sequentially (makes logs easier), but fallback search is parallel internally
  for (let idx = 0; idx < lines.length; idx++) {
    const line = lines[idx];
    if (!line || typeof line !== 'string') continue;
    if (!line.includes('moveonjoy.com')) continue;
    const fl = extractFlFromUrl(line);
    const path = extractPathFromUrl(line);
    if (!fl || !path) continue;
    // skip if line is already on a different fl (we only handle lines that reference currentMain originally)
    // but we still check all: if fl != currentMain we can still leave it (but we check restoration elsewhere)
    if (fl !== currentMain) continue;

    const mainUrl = `https://${currentMain}.moveonjoy.com/${path}`;
    const okMain = await fastCheckM3U(mainUrl);
    if (okMain) {
      log(`OK on main: ${path} (${currentMain})`);
      continue;
    }

    log(`Path ${path} not OK on ${currentMain}; searching fallback...`);
    const fallback = await findWorkingSubForPath(path, currentMain, currentMain);
    if (fallback) {
      const newUrl = `https://${fallback}.moveonjoy.com/${path}`;
      newLines[idx] = newUrl;
      changed = true;
      log(`Switched ${path} -> ${fallback}`);
    } else {
      log(`No working fl found for ${path}; leaving unchanged for next run`);
    }
  }
  return { newLines, changed };
}

// auto-restore: if currentMain now serves a path that exists elsewhere, restore
async function autoRestore(lines, currentMain) {
  const newLines = lines.slice();
  let changed = false;
  for (let idx = 0; idx < lines.length; idx++) {
    const line = lines[idx];
    if (!line || !line.includes('moveonjoy.com')) continue;
    const fl = extractFlFromUrl(line);
    const path = extractPathFromUrl(line);
    if (!fl || !path) continue;
    if (fl === currentMain) continue;
    const mainUrl = `https://${currentMain}.moveonjoy.com/${path}`;
    if (await ensureStable(mainUrl)) {
      newLines[idx] = mainUrl;
      changed = true;
      log(`Restored ${path} back to main ${currentMain}`);
    }
  }
  return { newLines, changed };
}

// Write + commit + push if changed (respects cooldown)
function gitCommitAndPushIfChanged(m3uPath, oldText, newLines) {
  const newText = newLines.join('\n') + '\n';
  if (newText === oldText) {
    log('No textual changes — nothing to commit.');
    return false;
  }

  // write file first so subsequent steps see it
  fsSync.writeFileSync(m3uPath, newText, 'utf8');
  log('Playlist written to disk.');

  // cooldown
  const now = Math.floor(Date.now() / 1000);
  let last = 0;
  if (fsSync.existsSync(LAST_UPDATE_FILE)) {
    try { last = parseInt(fsSync.readFileSync(LAST_UPDATE_FILE,'utf8')) || 0; } catch {}
  }
  if (COOLDOWN_SECONDS && (now - last) < COOLDOWN_SECONDS) {
    log('Cooldown active — skipping git push.');
    return true;
  }

  try {
    spawnSync('git', ['config','--global','user.email','actions@github.com'], { stdio: 'inherit' });
    spawnSync('git', ['config','--global','user.name','github-actions'], { stdio: 'inherit' });
    spawnSync('git', ['add', m3uPath], { stdio: 'inherit' });
    const res = spawnSync('git', ['commit', '-m', `Auto-update MoveOnJoy subdomains at ${new Date().toISOString()}`], { stdio: 'inherit' });
    if (res.status === 0) {
      spawnSync('git', ['push'], { stdio: 'inherit' });
      fsSync.writeFileSync(LAST_UPDATE_FILE, String(now), 'utf8');
      log('Changes pushed.');
    } else {
      log('Nothing to commit (git commit returned non-zero).');
    }
  } catch (e) {
    log('Git push failed:', e);
  }
  return true;
}

async function main() {
  log('MoveOnJoy Updater starting');
  log('Working dir:', process.cwd());
  const playlist = find_playlist();
  if (!playlist) {
    log('ERROR: us.m3u not found. Ensure PrimeVision/us.m3u exists.');
    process.exit(1);
  }

  const raw = fsSync.readFileSync(playlist, 'utf8');
  const lines = raw.split(/\r?\n/);

  // detect current main (first fl found)
  let currentMain = null;
  for (const L of lines) {
    const m = FL_RE.exec(L);
    if (m) { currentMain = m[1]; break; }
  }
  if (!currentMain) {
    log('ERROR: No flNN found in playlist.');
    process.exit(1);
  }
  log('Detected current main:', currentMain);

  // 1) if any channel on currentMain works -> main considered alive (sample)
  let mainAlive = false;
  let checked = 0;
  for (const L of lines) {
    if (L && L.includes(`${currentMain}.moveonjoy.com`)) {
      checked++;
      if (await fastCheckM3U(L)) { mainAlive = true; break; }
      if (checked >= SAMPLE_LIMIT) break;
    }
  }

  if (mainAlive) {
    log(`Main ${currentMain} appears alive (sample). Attempting auto-restore and per-channel repair.`);
    // try restore then per-channel fix
    const { newLines: restoredLines, changed: restoredChanged } = await autoRestore(lines, currentMain);
    if (restoredChanged) {
      log('Restored some channels to main.');
      gitCommitAndPushIfChanged(playlist, raw, restoredLines);
      return;
    }

    const { newLines: repairedLines, changed: repairedChanged } = await perChannelFailover(lines, currentMain);
    if (repairedChanged) {
      log('Applied per-channel fallbacks.');
      gitCommitAndPushIfChanged(playlist, raw, repairedLines);
      return;
    }

    log('No changes needed.');
    return;
  }

  // 2) main seems dead -> try to find fallback main
  log(`Main ${currentMain} appears offline (sample failed). Searching fallback main...`);
  const ranked = rankedSubs();
  let foundMain = null;
  // probe top candidates quickly (sample paths)
  for (const cand of ranked.slice(0, MAX_ATTEMPTS)) {
    if (cand === currentMain) continue;
    let anyOk = false;
    // sample any lines referencing cand; if none, sample some arbitrary channels on cand (constructable)
    for (const L of lines) {
      if (L && L.includes(`${cand}.moveonjoy.com`)) {
        if (await fastCheckM3U(L)) { anyOk = true; break; }
      }
    }
    if (anyOk) { foundMain = cand; break; }
  }

  if (!foundMain) {
    log('No fallback main found quickly. Applying per-channel fallbacks only.');
    const { newLines: repairedLines, changed: repairedChanged } = await perChannelFailover(lines, currentMain);
    if (repairedChanged) {
      gitCommitAndPushIfChanged(playlist, raw, repairedLines);
      return;
    }
    log('No changes possible.');
    return;
  }

  log('Found fallback main:', foundMain, '— migrating main channels where possible.');
  const newLines = lines.slice();
  let changed = false;
  // attempt switching non-special paths to fallback main if stable
  for (let idx = 0; idx < lines.length; idx++) {
    const L = lines[idx];
    if (!L || !L.includes('moveonjoy.com')) continue;
    const pathPart = extractPathFromUrl(L);
    if (!pathPart) continue;
    // skip if already on fallback or special
    const testUrl = `https://${foundMain}.moveonjoy.com/${pathPart}`;
    if (await fastCheckM3U(testUrl) && await ensureStable(testUrl)) {
      newLines[idx] = testUrl;
      changed = true;
      log(`Switched ${pathPart} -> ${foundMain}`);
    }
  }

  if (changed) {
    gitCommitAndPushIfChanged(playlist, raw, newLines);
  } else {
    log('Fallback main found but no stable matching paths on it; nothing changed.');
  }
}

main().catch(err => { log('Fatal error:', err); process.exit(1); });