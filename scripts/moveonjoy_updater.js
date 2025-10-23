#!/usr/bin/env node
/**
 * MoveOnJoy Updater (Node.js) — Per-channel failover + auto-restore (balanced fast mode)
 *
 * Drop into scripts/moveonjoy_updater.js and run with: node scripts/moveonjoy_updater.js
 *
 * Requirements:
 *   npm install axios
 *
 * Behavior:
 *  - Detects playlist (PrimeVision/us.m3u or recursive)
 *  - Keeps main subdomain if ANY channel on it is playable
 *  - Moves only offline channels to a working flNN
 *  - Restores channels back to main when main serves the path again
 *  - Fast checks: HEAD-first + small-range GET for first segment
 *  - Stability: verify candidate 3x before accepting (configurable)
 *  - Git commit & push only on real changes (cooldown)
 */

const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');
const axios = require('axios');
const { spawnSync } = require('child_process');

/// ============ CONFIG ============
const PLAYLIST_CANDIDATES = [
  path.join('PrimeVision', 'us.m3u'),
  path.join('IPTV-LIVE', 'PrimeVision', 'us.m3u'),
  path.join('gtvservices5', 'IPTV-LIVE', 'PrimeVision', 'us.m3u'),
  'us.m3u'
];

const SUB_MIN = 3;
const SUB_MAX = 50;
const SUB_RANGE = Array.from({length: SUB_MAX - SUB_MIN + 1}, (_, i) => SUB_MAX - i).map(i => `fl${i}`); // fl50..fl3

const RETRIES = 2;
const RETRY_DELAY = 600; // ms
const SAMPLE_LIMIT = 3;   // how many sample channels to test to judge a subdomain alive (small = fast)
const COOLDOWN_SECONDS = 3600;
const LAST_UPDATE_FILE = '.moveonjoy_last_update';

// stability checks for candidate fallback
const STABLE_TRIES = 3;
const STABLE_DELAY_MS = 700;

// concurrency
const WORKER_BATCH = 8; // parallel batch size for probing

// special channels to prefer own host (exact path)
const SPECIAL_CHANNEL_PATHS = new Set([
  'DISNEY/index.m3u8'
]);

// regex
const FL_RE = /https:\/\/(fl\d+)\.moveonjoy\.com\/([^\s]+)/i;

// HTTP settings
const HEAD_TIMEOUT = 3000;
const GET_TIMEOUT = 6000;
const RANGE_BYTE_FETCH = 'bytes=0-65535'; // fetch up to 64KB of first segment

// ============ UTIL ============
function log(...args) {
  const ts = (new Date()).toISOString();
  console.log(`[${ts}]`, ...args);
}

async function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

async function find_playlist() {
  for (const p of PLAYLIST_CANDIDATES) {
    try {
      if (await fs.stat(p).then(()=>true).catch(()=>false)) {
        log('Found playlist at:', p);
        return p;
      }
    } catch(e) { }
  }
  // recursive fallback
  async function recursiveSearch(dir) {
    for await (const f of await fs.opendir(dir)) {
      const full = path.join(dir, f.name);
      if (f.name === 'us.m3u') return full;
      if (f.isDirectory()) {
        const res = await recursiveSearch(full);
        if (res) return res;
      }
    }
    return null;
  }
  try {
    const res = await recursiveSearch('.');
    if (res) log('Found playlist via recursive search:', res);
    return res;
  } catch (e) {
    return null;
  }
}

// axios helpers
async function doHead(url, timeout=HEAD_TIMEOUT) {
  try {
    return await axios.head(url, { timeout, maxRedirects: 5, validateStatus: null });
  } catch (e) {
    return null;
  }
}
async function doGetBytes(url, timeout=GET_TIMEOUT, rangeHeader=RANGE_BYTE_FETCH) {
  try {
    const res = await axios.get(url, {
      timeout,
      responseType: 'arraybuffer',
      headers: { Range: rangeHeader },
      maxRedirects: 5,
      validateStatus: null
    });
    return res;
  } catch (e) {
    return null;
  }
}

// lightweight "playlist exists" check: HEAD => content-type, or small GET and look for segment references
async function fastCheckUrlM3U(url) {
  // HEAD
  const head = await doHead(url);
  if (head && head.status >= 200 && head.status < 400) {
    const ct = (head.headers['content-type'] || '').toLowerCase();
    if (ct.includes('mpegurl') || ct.includes('vnd.apple.mpegurl')) return true;
    // ambiguous -> try light GET
    const g = await doGetBytes(url);
    if (g && g.status >= 200 && g.status < 400) {
      const text = Buffer.from(g.data).toString('utf8', 0, 5000);
      // look for TS or m3u8 lines
      const lines = text.split(/\r?\n/);
      for (const L of lines) {
        const s = L.trim();
        if (!s || s.startsWith('#')) continue;
        if (s.endsWith('.ts') || s.endsWith('.m3u8')) return true;
      }
      return false;
    }
  }
  return false;
}

// check that first media segment contains video-like data (MPEG-TS sync or NAL units)
function bufferHasVideoMarkers(buf) {
  if (!buf || buf.length < 16) return false;
  const arr = Buffer.from(buf);
  // check for MPEG-TS sync byte 0x47 at start or periodic (fast heuristic)
  if (arr[0] === 0x47) return true;
  // search for NAL start codes 00 00 00 01 followed by SPS(0x67) or IDR(0x65)
  const pattern1 = Buffer.from([0x00,0x00,0x00,0x01,0x67]);
  const pattern2 = Buffer.from([0x00,0x00,0x00,0x01,0x65]);
  const pattern3 = Buffer.from([0x00,0x00,0x00,0x01,0x40]); // H265 VPS
  if (arr.includes(pattern1) || arr.includes(pattern2) || arr.includes(pattern3)) return true;
  return false;
}

// combined playable check: playlist -> first segment HEAD/GET -> check video markers
async function checkStreamPlayable(url) {
  // fast m3u check
  if (!(await fastCheckUrlM3U(url))) return false;
  // parse playlist (GET small)
  const r = await doGetBytes(url);
  if (!r || r.status >= 400) return false;
  let text;
  try { text = Buffer.from(r.data).toString('utf8'); } catch(e){ return false; }
  // find first candidate segment line
  for (const L of text.split(/\r?\n/)) {
    const s = L.trim();
    if (!s || s.startsWith('#')) continue;
    // candidate
    let segUrl;
    if (/^https?:\/\//i.test(s)) segUrl = s;
    else segUrl = url.replace(/\/[^\/]*$/, '') + '/' + s;
    // try HEAD first
    const h = await doHead(segUrl);
    if (h && h.status >= 200 && h.status < 400) {
      // fetch short sample of segment bytes
      const segGet = await doGetBytes(segUrl);
      if (segGet && segGet.status >= 200 && segGet.status < 400) {
        if (bufferHasVideoMarkers(segGet.data)) return true;
        else return false; // segment exists but no video markers
      }
    }
    break; // test only first candidate
  }
  return false;
}

// stability: test URL n times quickly
async function ensureStable(url, tries=STABLE_TRIES, delayMs=STABLE_DELAY_MS) {
  for (let i=1;i<=tries;i++){
    const ok = await fastCheckUrlM3U(url);
    if (!ok) {
      log(`Stability: candidate ${url} failed quick check ${i}/${tries}`);
      return false;
    }
    // also do a fast segment presence + video marker check once before finalizing (on last try)
    if (i === tries) {
      const playOk = await checkStreamPlayable(url);
      if (!playOk) {
        log(`Stability: candidate ${url} failed deep playable check`);
        return false;
      }
    }
    if (i < tries) await sleep(delayMs);
  }
  log(`Stability: ${url} passed ${tries}/${tries}`);
  return true;
}

function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }

// playlist parse helpers
function splitLines(text){ return text.split(/\r?\n/); }
function joinLines(lines){ return lines.join('\n') + (lines.length && !lines[lines.length-1].endsWith('\n') ? '\n' : ''); }

function linesUsingSubdomain(lines, subdomain){
  const out = [];
  for (let i=0;i<lines.length;i++){
    const line = lines[i];
    if (!line || !line.includes('http') || !line.includes(`${subdomain}.moveonjoy.com`)) continue;
    const m = FL_RE.exec(line);
    if (m) out.push({ idx: i, url: m[0], path: m[2] });
  }
  return out;
}

function enumerateAllFL(lines){
  const out = [];
  for (let i=0;i<lines.length;i++){
    const line = lines[i];
    if (!line || !line.includes('http') || !line.includes('moveonjoy.com')) continue;
    const m = FL_RE.exec(line);
    if (m) out.push({ idx: i, url: m[0], path: m[2], sub: m[1] });
  }
  return out;
}

function extractCurrentSubdomain(lines){
  for (const line of lines){
    const m = FL_RE.exec(line);
    if (m) return m[1];
  }
  return null;
}

// search fallback for path — balanced search order (S2): try nearby offsets first then expand up to maxAttempts
function buildBalancedSubSearch(exclude, maxAttempts=8, current=null){
  // create array of flNN that tries nearby numbers first relative to current if provided
  const subs = SUB_RANGE.slice();
  if (current && current.startsWith('fl')) {
    const curNum = parseInt(current.replace('fl',''),10);
    const results = [];
    let step = 1;
    while (results.length < Math.min(maxAttempts, subs.length)) {
      const low = curNum - step;
      const high = curNum + step;
      if (low >= SUB_MIN) results.push(`fl${low}`);
      if (results.length >= maxAttempts) break;
      if (high <= SUB_MAX) results.push(`fl${high}`);
      if (results.length >= maxAttempts) break;
      step++;
      if (low < SUB_MIN && high > SUB_MAX) break;
    }
    // fill remaining from highest->lowest skipping exclude and current
    for (const s of subs) {
      if (results.length >= maxAttempts) break;
      if (s === exclude) continue;
      if (s === current) continue;
      if (!results.includes(s)) results.push(s);
    }
    return results;
  }
  // fallback default: top N from SUB_RANGE excluding exclude
  const res = [];
  for (const s of subs){
    if (s === exclude) continue;
    res.push(s);
    if (res.length >= maxAttempts) break;
  }
  return res;
}

// find working subdomain for a path using batch parallelism and ensureStable
async function findWorkingSubdomainForPath(path, excludeSub=null, current=null, maxAttempts=8){
  const searchList = buildBalancedSubSearch(excludeSub, maxAttempts, current);
  // probe in small batches
  for (let i=0;i<searchList.length;i+=WORKER_BATCH){
    const batch = searchList.slice(i, i+WORKER_BATCH);
    const promises = batch.map(async (sub) => {
      const url = `https://${sub}.moveonjoy.com/${path}`;
      try {
        const ok = await fastCheckUrlM3U(url);
        return ok ? { sub, url } : null;
      } catch(e){ return null; }
    });
    const results = await Promise.all(promises);
    for (const r of results){
      if (r) {
        // verify stability
        if (await ensureStable(r.url)) return r.sub;
      }
    }
  }
  return null;
}

// find any fallback main subdomain (fast)
async function findAnyFallbackMain(lines, excludeSub=null){
  for (const sub of SUB_RANGE){
    if (sub === excludeSub) continue;
    // sample a few lines referencing this sub for speed
    const sample = linesUsingSubdomain(lines, sub).slice(0, SAMPLE_LIMIT);
    if (sample.length === 0) continue;
    // check them quickly (serial or small parallel)
    const checks = await Promise.all(sample.map(e => fastCheckUrlM3U(e.url)));
    if (checks.some(Boolean)) return sub;
  }
  return null;
}

// per-channel failover
async function perChannelFailover(lines, currentMain){
  const newLines = lines.slice();
  let changed = false;
  const entries = linesUsingSubdomain(lines, currentMain);
  if (!entries.length) return { newLines, changed };
  // find paths that fail on main
  const toFix = [];
  for (const e of entries){
    const testUrl = `https://${currentMain}.moveonjoy.com/${e.path}`;
    const ok = await fastCheckUrlM3U(testUrl);
    if (ok) continue;
    toFix.push(e);
  }
  if (!toFix.length) return { newLines, changed };
  // process toFix in parallel batches
  const promises = [];
  for (const e of toFix){
    promises.push((async () => {
      const fallback = await findWorkingSubdomainForPath(e.path, currentMain, currentMain, 8);
      if (fallback){
        const newUrl = `https://${fallback}.moveonjoy.com/${e.path}`;
        log(`Switching ${e.path} (line ${e.idx}) -> ${fallback}`);
        newLines[e.idx] = newLines[e.idx].replace(/https:\/\/fl\d+\.moveonjoy\.com\/[^\s]+/i, newUrl);
        return true;
      } else {
        log(`No fallback found for ${e.path}`);
        return false;
      }
    })());
  }
  const results = await Promise.all(promises);
  if (results.some(Boolean)) changed = true;
  return { newLines, changed };
}

// auto-restore channels that are on other flNN back to main if main serves the path again
async function autoRestoreToMain(lines, currentMain){
  const newLines = lines.slice();
  let changed = false;
  const all = enumerateAllFL(lines);
  const toTest = [];
  for (const e of all){
    if (e.sub === currentMain) continue;
    toTest.push({idx:e.idx, path:e.path, sub:e.sub});
  }
  if (!toTest.length) return { newLines, changed };
  // probe in parallel
  const promises = toTest.map(async t => {
    const mainTest = `https://${currentMain}.moveonjoy.com/${t.path}`;
    if (await ensureStable(mainTest)) {
      newLines[t.idx] = newLines[t.idx].replace(/https:\/\/fl\d+\.moveonjoy\.com\/[^\s]+/i, mainTest);
      log(`Restored ${t.path} back to main ${currentMain}`);
      return true;
    }
    return false;
  });
  const res = await Promise.all(promises);
  if (res.some(Boolean)) changed = true;
  return { newLines, changed };
}

// git commit & push helper (with cooldown)
function gitCommitAndPushIfChanged(playlistPath, oldText, newLines){
  const newText = newLines.join('\n');
  if (newText === oldText) {
    log('No textual changes — nothing to commit');
    return false;
  }
  const now = Math.floor(Date.now() / 1000);
  let last = 0;
  try {
    if (fsSync.existsSync(LAST_UPDATE_FILE)) {
      last = parseInt(fsSync.readFileSync(LAST_UPDATE_FILE, 'utf8')) || 0;
    }
  } catch (e) { last = 0; }

  // write file immediately (so runner sees update)
  try {
    fsSync.writeFileSync(playlistPath, newText + (newText.endsWith('\n') ? '' : '\n'), 'utf8');
    log('Wrote playlist to disk.');
  } catch (e) {
    log('Failed to write playlist:', e);
    return false;
  }

  if (COOLDOWN_SECONDS && (now - last) < COOLDOWN_SECONDS) {
    log(`Cooldown active (${now-last}s elapsed) — skipping git push.`);
    return true;
  }

  try {
    spawnSync('git', ['config', '--global', 'user.email', 'actions@github.com'], { stdio: 'inherit' });
    spawnSync('git', ['config', '--global', 'user.name', 'github-actions'], { stdio: 'inherit' });
    spawnSync('git', ['add', playlistPath], { stdio: 'inherit' });
    const res = spawnSync('git', ['commit', '-m', `Auto-update MoveOnJoy subdomains at ${new Date().toISOString()}`], { stdio: 'inherit' });
    if (res.status === 0) {
      spawnSync('git', ['push'], { stdio: 'inherit' });
      fsSync.writeFileSync(LAST_UPDATE_FILE, String(now), 'utf8');
      log('Git push completed.');
    } else {
      log('Nothing to commit (commit returned non-zero).');
    }
  } catch (e) {
    log('Git operation failed:', e);
  }
  return true;
}

// ============ MAIN ============
(async function main(){
  log('MoveOnJoy Updater (Node.js) starting — per-channel failover + autorestore (balanced)');
  log('Working dir:', process.cwd());

  const playlistPath = await find_playlist();
  if (!playlistPath) {
    log('ERROR: Could not find us.m3u in repository. Ensure PrimeVision/us.m3u exists.');
    process.exit(1);
  }

  const raw = await fs.readFile(playlistPath, 'utf8');
  const lines = splitLines(raw);

  const currentMain = extractCurrentSubdomain(lines);
  if (!currentMain) {
    log('ERROR: no flNN moveonjoy domain found in playlist.');
    process.exit(1);
  }
  log('Detected main subdomain:', currentMain);

  // 1) Check if any channel on current main is playable
  const mainAlive = await (async () => {
    const entries = linesUsingSubdomain(lines, currentMain).slice(0, SAMPLE_LIMIT);
    if (!entries.length) return false;
    for (const e of entries){
      log('Probing sample', e.url);
      if (await fastCheckUrlM3U(e.url)) {
        log(' -> sample playable -> main considered alive.');
        return true;
      }
    }
    return false;
  })();

  if (mainAlive){
    log(`Main ${currentMain} appears alive.`);
    // try restoring channels back to main
    const { newLines: restoredLines, changed: restoredChanged } = await autoRestoreToMain(lines, currentMain);
    if (restoredChanged) {
      log('Restored channels back to main; committing (if not in cooldown).');
      gitCommitAndPushIfChanged(playlistPath, raw, restoredLines);
      return;
    }
    // per-channel failover for channels on main that have become individually offline
    const { newLines: repairedLines, changed: repairedChanged } = await perChannelFailover(lines, currentMain);
    if (repairedChanged) {
      log('Applied per-channel fallbacks; committing (if not in cooldown).');
      gitCommitAndPushIfChanged(playlistPath, raw, repairedLines);
      return;
    }
    log('No changes needed.');
    return;
  }

  // 2) main is not alive (no sample playable)
  log(`Main ${currentMain} appears offline (sample failed). Searching fallback main...`);
  const fallbackMain = await findAnyFallbackMain(lines, currentMain);
  if (!fallbackMain) {
    log('No fallback main found quickly. Attempting per-channel fallbacks...');
    const { newLines: repairedLines, changed: repairedChanged } = await perChannelFailover(lines, currentMain);
    if (repairedChanged) {
      gitCommitAndPushIfChanged(playlistPath, raw, repairedLines);
      return;
    }
    log('No changes possible.');
    return;
  }

  log('Found fallback main:', fallbackMain, ' — migrating main channels where possible.');
  let newLines = lines.slice();
  let changed = false;
  // for every fl line (non-special) try to switch to fallback if that path works there (fast + stability)
  const allFl = enumerateAllFL(lines);
  const checks = [];
  for (const e of allFl){
    if (SPECIAL_CHANNEL_PATHS.has(e.path)) continue;
    // create fast check promise
    checks.push((async ()=>{
      const testUrl = `https://${fallbackMain}.moveonjoy.com/${e.path}`;
      if (await fastCheckUrlM3U(testUrl)) {
        if (await ensureStable(testUrl)) {
          newLines[e.idx] = newLines[e.idx].replace(/https:\/\/fl\d+\.moveonjoy\.com\/[^\s]+/i, testUrl);
          log('Switched path', e.path, '->', fallbackMain);
          return true;
        }
      }
      return false;
    })());
  }
  const checkResults = await Promise.all(checks);
  if (checkResults.some(Boolean)) {
    changed = true;
  }

  if (changed) {
    gitCommitAndPushIfChanged(playlistPath, raw, newLines);
  } else {
    log('Found fallback main but no stable matching paths available on it; no changes done.');
  }

})();