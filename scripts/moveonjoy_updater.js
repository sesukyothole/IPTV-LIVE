#!/usr/bin/env node
/**
 * moveonjoy_updater_full.js
 * Full intelligent MoveOnJoy Updater (Node.js)
 */

const fs = require('fs');
const fsSync = require('fs');
const path = require('path');
const axios = require('axios');
const { spawnSync } = require('child_process');

const PLAYLIST_REL = path.join('PrimeVision', 'us.m3u');
const PLAYLIST_PATH = path.resolve(PLAYLIST_REL);
const BACKUP_PATH = PLAYLIST_PATH + '.bak';
const RANK_FILE = path.resolve('.subdomain_health.json');
const DOCS_DIR = path.resolve('docs'); // for GitHub Pages
const DASHBOARD_HTML = path.join(DOCS_DIR, 'index.html');

const SUB_MIN = 3;
const SUB_MAX = 50;
const DEFAULT_SEARCH_ATTEMPTS = 12; // balanced S2 but wider, uses learned order first
const STABLE_TRIES = 3;
const STABLE_DELAY_MS = 700;
const SAMPLE_LIMIT = 3;
const THREADS = 12;
const COOLDOWN_SECONDS = 3600;
const LAST_UPDATE = '.moveonjoy_last_update';

const FL_RE = /https?:\/\/(fl\d+)\.moveonjoy\.com\/([^\s]+)/i;
const SPECIAL_PATHS = new Set(['DISNEY/index.m3u8']);

// helper logging
function log(...a){ console.log(new Date().toISOString(), ...a); }
function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }

async function findPlaylist(){
  if (fsSync.existsSync(PLAYLIST_PATH)) return PLAYLIST_PATH;
  // recursive search
  const found = (function walk(dir){
    const L = fsSync.readdirSync(dir, { withFileTypes: true });
    for (const e of L){
      const p = path.join(dir, e.name);
      if (e.isFile() && e.name === 'us.m3u') return p;
      if (e.isDirectory()){
        const r = walk(p);
        if (r) return r;
      }
    }
    return null;
  })('.');
  return found;
}

async function axiosHead(url, timeout=3000){
  try {
    return await axios.head(url, { timeout, maxRedirects: 5, validateStatus: null });
  } catch(e){ return null; }
}
async function axiosGetBytes(url, timeout=6000, range='bytes=0-65535'){
  try {
    return await axios.get(url, { timeout, responseType: 'arraybuffer', headers: { Range: range }, maxRedirects: 5, validateStatus: null });
  } catch(e){ return null; }
}

// quick check: HEAD then small GET if needed
async function fastCheckM3U(url){
  const h = await axiosHead(url);
  if (h && h.status >= 200 && h.status < 400){
    const ct = (h.headers['content-type'] || '').toLowerCase();
    if (ct.includes('mpegurl') || ct.includes('vnd.apple.mpegurl')) return true;
    // try small GET
    const g = await axiosGetBytes(url);
    if (g && g.status >= 200 && g.status < 400){
      const txt = Buffer.from(g.data).toString('utf8',0,5000);
      for (const line of txt.split(/\r?\n/)){
        const s = line.trim();
        if (!s || s.startsWith('#')) continue;
        if (s.endsWith('.ts') || s.endsWith('.m3u8')) return true;
      }
    }
  }
  return false;
}

function bufferHasVideoMarkers(buf){
  if (!buf || buf.length < 16) return false;
  const arr = Buffer.from(buf);
  if (arr[0] === 0x47) return true; // ts sync
  const patterns = [ Buffer.from([0,0,0,1,0x67]), Buffer.from([0,0,0,1,0x65]), Buffer.from([0,0,0,1,0x40]) ];
  for(const p of patterns) if (arr.includes(p)) return true;
  return false;
}

async function checkStreamPlayable(url){
  if (! await fastCheckM3U(url)) return false;
  const g = await axiosGetBytes(url);
  if (!g || g.status >= 400) return false;
  const text = Buffer.from(g.data).toString('utf8');
  for (const L of text.split(/\r?\n/)){
    const s = L.trim();
    if (!s || s.startsWith('#')) continue;
    let seg = s;
    if (!/^https?:\/\//i.test(s)) seg = url.replace(/\/[^\/]*$/, '') + '/' + s;
    const segHead = await axiosHead(seg);
    if (segHead && segHead.status >=200 && segHead.status < 400){
      const segGet = await axiosGetBytes(seg);
      if (segGet && segGet.status >=200 && segGet.status < 400){
        return bufferHasVideoMarkers(segGet.data);
      }
    }
    break;
  }
  return false;
}

async function ensureStable(url, tries=STABLE_TRIES, delay=STABLE_DELAY_MS){
  for (let i=1;i<=tries;i++){
    // do a fast HEAD-first check
    const okFast = await fastCheckM3U(url);
    if (!okFast){
      log(`Stability: fast check failed for ${url} on ${i}/${tries}`);
      return false;
    }
    // on final try do deeper playable check
    if (i === tries){
      const okPlay = await checkStreamPlayable(url);
      if (!okPlay){
        log(`Stability: deep playable check failed for ${url}`);
        return false;
      }
    }
    if (i < tries) await sleep(delay);
  }
  return true;
}

// subdomain ranking store: counts successes and failures per flXX
function loadRank(){
  try { return JSON.parse(fsSync.readFileSync(RANK_FILE,'utf8')); } catch(e){ return {}; }
}
function saveRank(rank){ try{ fsSync.writeFileSync(RANK_FILE, JSON.stringify(rank, null, 2),'utf8'); }catch(e){} }
function bumpRank(sub, ok){
  const r = loadRank();
  if (!r[sub]) r[sub] = { success:0, fail:0, last: null };
  if (ok) r[sub].success++;
  else r[sub].fail++;
  r[sub].last = Date.now();
  saveRank(r);
}
function rankedSubs(current=null){
  // build list and sort by success rate then success count then recency. include full fl range default if missing
  const r = loadRank();
  const arr = [];
  for (let n=SUB_MAX; n>=SUB_MIN; n--){
    const s = `fl${n}`;
    const data = r[s] || { success:0, fail:0, last:null };
    const rate = data.success + data.fail === 0 ? 0 : data.success / (data.success + data.fail);
    arr.push({ sub:s, rate, success:data.success, fail:data.fail, last:data.last });
  }
  // sort: higher rate first, then success, then newer
  arr.sort((a,b)=>{
    if (b.rate !== a.rate) return b.rate - a.rate;
    if (b.success !== a.success) return b.success - a.success;
    return (b.last||0) - (a.last||0);
  });
  // if current present, try to keep it near front? We'll return the full sorted list; searching logic will pick top K around current later
  return arr.map(x=>x.sub);
}

function extractFlFromUrl(url){
  const m = FL_RE.exec(url);
  return m ? m[1] : null;
}

function extractPathFromUrl(url){
  const m = FL_RE.exec(url);
  return m ? m[2] : null;
}

function replaceFlInUrl(url, fl){
  return url.replace(/fl\d+/, fl);
}

// balanced S2 search builder: prefer learned order, but attempt up to maxAttempts
function buildBalancedSearchList(currentFl, maxAttempts=DEFAULT_SEARCH_ATTEMPTS){
  const ranked = rankedSubs(currentFl); // fl list high->low by history
  // start with ranked order but put currentFl near middle; remove current from list
  const list = ranked.filter(s => s !== currentFl);
  // cap list length
  return list.slice(0, maxAttempts);
}

// read & write utilities
function readLines(p){ return fsSync.readFileSync(p,'utf8').split(/\r?\n/); }
function writeLines(p, lines){ fsSync.writeFileSync(p, lines.join('\n') + '\n', 'utf8'); }

// main search for path fallback
async function findWorkingSubForPath(path, exclude=null, current=null){
  const candidates = buildBalancedSearchList(current, DEFAULT_SEARCH_ATTEMPTS);
  for (const sub of candidates){
    if (sub === exclude) continue;
    const url = `https://${sub}.moveonjoy.com/${path}`;
    try {
      const ok = await fastCheckM3U(url);
      if (!ok) continue;
      if (await ensureStable(url)){
        bumpRank(sub, true);
        return sub;
      } else {
        bumpRank(sub, false);
      }
    } catch(e){
      bumpRank(sub, false);
    }
  }
  return null;
}

// Per-channel fallback: change only lines referencing currentMain that fail
async function perChannelFailover(lines, currentMain){
  let changed = false;
  const newLines = lines.slice();
  for (let idx=0; idx<lines.length; idx++){
    const line = lines[idx];
    if (!line || !line.includes('moveonjoy.com')) continue;
    const fl = extractFlFromUrl(line);
    if (fl !== currentMain) continue;
    const path = extractPathFromUrl(line);
    if (!path) continue;
    // test path on current main quickly
    const mainUrl = `https://${currentMain}.moveonjoy.com/${path}`;
    const okMain = await fastCheckM3U(mainUrl);
    if (okMain) continue; // fine
    log(`Channel ${path} fails on ${currentMain}. Searching fallback...`);
    const fallback = await findWorkingSubForPath(path, currentMain, currentMain);
    if (fallback){
      const newUrl = `https://${fallback}.moveonjoy.com/${path}`;
      newLines[idx] = newUrl;
      changed = true;
      log(`Replaced ${path} → ${newUrl}`);
    } else {
      // comment out (A2) with reason and timestamp after repeated fails (safety: do only after 2 search attempts)
      log(`No fallback found for ${path}; commenting out line.`);
      newLines[idx] = `# OFFLINE: ${new Date().toISOString()} - ${line}`;
      changed = true;
    }
  }
  return { newLines, changed };
}

// Auto-restore: if currentMain starts serving a path again, restore lines that point to other flXX
async function autoRestore(lines, currentMain){
  let changed = false;
  const newLines = lines.slice();
  // check lines that reference moveonjoy but not currentMain
  for (let idx=0; idx<lines.length; idx++){
    const line = lines[idx];
    if (!line || !line.includes('moveonjoy.com')) continue;
    const fl = extractFlFromUrl(line);
    if (!fl || fl === currentMain) continue;
    const path = extractPathFromUrl(line);
    if (!path) continue;
    const mainTry = `https://${currentMain}.moveonjoy.com/${path}`;
    if (await ensureStable(mainTry)){
      newLines[idx] = mainTry;
      changed = true;
      log(`Restored ${path} back to main ${currentMain}`);
    }
  }
  return { newLines, changed };
}

function gitCommitAndPushIfChanged(filePath, oldText, newLines){
  const newText = newLines.join('\n') + '\n';
  if (newText === oldText) { log('No changes to commit'); return false; }
  try { fsSync.writeFileSync(BACKUP_PATH, oldText, 'utf8'); } catch(e){}
  fsSync.writeFileSync(filePath, newText, 'utf8');
  log('Playlist written to disk and backed up.');

  // cooldown
  const now = Math.floor(Date.now()/1000);
  let last = 0;
  try { if (fsSync.existsSync(LAST_UPDATE)) last = parseInt(fsSync.readFileSync(LAST_UPDATE,'utf8'))||0; } catch(e){ last=0; }
  if (COOLDOWN_SECONDS && (now - last) < COOLDOWN_SECONDS){
    log('Cooldown active — skipping git push.');
    return true;
  }

  try {
    spawnSync('git', ['config', '--global', 'user.email', 'actions@github.com']);
    spawnSync('git', ['config', '--global', 'user.name', 'github-actions']);
    spawnSync('git', ['add', filePath], { stdio:'inherit' });
    const res = spawnSync('git', ['commit', '-m', `Auto-update MoveOnJoy subdomains at ${new Date().toISOString()}`], { stdio:'inherit' });
    if (res.status === 0) {
      spawnSync('git', ['push'], { stdio:'inherit' });
      fsSync.writeFileSync(LAST_UPDATE, String(now),'utf8');
      log('Changes pushed.');
    } else {
      log('Nothing to commit (git returned no change).');
    }
  } catch(e){
    log('Git operation failed:', e);
  }
  return true;
}

// Build a small docs HTML page for dashboard (C1)
function buildDashboardHtml(channelStatuses, rankedList){
  let rows = '';
  for (const s of channelStatuses){
    rows += `<tr><td>${s.title||'?'}</td><td>${s.path}</td><td>${s.url}</td><td>${s.status}</td><td>${s.note||''}</td></tr>\n`;
  }
  const rankedHtml = rankedList.map((r,i)=>`<li>${r}</li>`).join('\n');
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>MoveOnJoy Updater Dashboard</title>
<style>body{font-family:system-ui,Arial}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}</style>
</head><body>
<h1>MoveOnJoy Updater Dashboard</h1>
<p>Generated: ${new Date().toISOString()}</p>
<h2>Subdomain ranking (most reliable → )</h2><ol>${rankedHtml}</ol>
<h2>Channels</h2>
<table><thead><tr><th>Title</th><th>Path</th><th>URL</th><th>Status</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table>
</body></html>`;
}

// main run
(async function main(){
  try {
    log('Starting MoveOnJoy Updater FULL');
    const playlist = await findPlaylist();
    if (!playlist) { log('us.m3u not found; abort'); process.exit(1); }
    log('Playlist:', playlist);
    const raw = fsSync.readFileSync(playlist,'utf8');
    const lines = raw.split(/\r?\n/);

    const currentMain = (function findFirstFl(){
      for (const L of lines){
        const m = FL_RE.exec(L);
        if (m) return m[1];
      }
      return null;
    })();
    if (!currentMain){ log('No flNN main found; abort'); process.exit(1); }
    log('Detected current main', currentMain);

    // 1) If main alive by any sample → auto-restore then per-channel fix
    let sampleAlive = false;
    let sampleCount = 0;
    for (const e of lines){
      if (e && e.includes(currentMain) && e.includes('moveonjoy.com')){
        sampleCount++;
        const ok = await fastCheckM3U(e);
        if (ok){ sampleAlive = true; break; }
        if (sampleCount >= SAMPLE_LIMIT) break;
      }
    }

    if (sampleAlive){
      log('Main appears alive; attempting restore & per-channel fix');
      const { newLines: restored, changed: restoredChanged } = await autoRestore(lines, currentMain);
      if (restoredChanged){ gitCommitAndPushIfChanged(playlist, raw, restored); return; }
      const { newLines: fixed, changed: fixedChanged } = await perChannelFailover(lines, currentMain);
      if (fixedChanged){ gitCommitAndPushIfChanged(playlist, raw, fixed); return; }
      log('No changes required.');
    } else {
      log('Main appears offline (sample failed). Searching fallback main');
      // find any fallback main (fast check on ranked subs)
      const ranked = rankedSubs(currentMain);
      let foundMain = null;
      for (const cand of ranked.slice(0, DEFAULT_SEARCH_ATTEMPTS)){
        if (cand === currentMain) continue;
        // test a sample of channels for cand
        let anyOk = false;
        for (const L of lines){
          if (L && L.includes(`${cand}.moveonjoy.com`)){
            if (await fastCheckM3U(L)) { anyOk = true; break; }
          }
        }
        if (anyOk){ foundMain = cand; break; }
      }
      if (!foundMain){
        log('No fallback main found; attempt per-channel fallbacks');
        const { newLines: fixed, changed: fixedChanged } = await perChannelFailover(lines, currentMain);
        if (fixedChanged){ gitCommitAndPushIfChanged(playlist, raw, fixed); return; }
        log('No changes possible.');
      } else {
        log('Found fallback main', foundMain, ' — migrating matching paths');
        const newLines = lines.slice();
        let changed = false;
        for (let idx=0; idx<lines.length; idx++){
          const L = lines[idx];
          if (!L || !L.includes('moveonjoy.com')) continue;
          const pathPart = extractPathFromUrl(L);
          if (!pathPart) continue;
          if (SPECIAL_PATHS.has(pathPart)) continue;
          const testUrl = `https://${foundMain}.moveonjoy.com/${pathPart}`;
          if (await fastCheckM3U(testUrl) && await ensureStable(testUrl)){
            newLines[idx] = testUrl;
            changed = true;
            log('Switched',pathPart,'->',foundMain);
          }
        }
        if (changed) gitCommitAndPushIfChanged(playlist, raw, newLines);
        else log('Fallback main found but no matching stable paths on it.');
      }
    }

    // update dashboard and ranking file
    try {
      const rankList = rankedSubs(currentMain);
      // compute channel statuses for dashboard
      const chs = [];
      for (const L of lines){
        if (!L) continue;
        let status='N/A', note='';
        if (L.includes('moveonjoy.com')) {
          const fl = extractFlFromUrl(L);
          const pth = extractPathFromUrl(L);
          const playable = await fastCheckM3U(L);
          status = playable ? 'ONLINE' : 'OFFLINE';
          chs.push({ title:'', path: pth||'', url: L, status, note });
        }
      }
      if (!fsSync.existsSync(DOCS_DIR)) fsSync.mkdirSync(DOCS_DIR);
      fsSync.writeFileSync(DASHBOARD_HTML, buildDashboardHtml(chs, rankList), 'utf8');
      // commit docs
      spawnSync('git', ['add', DASHBOARD_HTML]);
      spawnSync('git', ['commit', '-m', `Update MoveOnJoy dashboard ${new Date().toISOString()}`], { stdio:'inherit' });
      spawnSync('git', ['push'], { stdio:'inherit' });
    } catch(e){ log('Dashboard update failed:', e); }

    log('Done run.');
  } catch(e){ log('Fatal error:', e); process.exit(1); }
})();