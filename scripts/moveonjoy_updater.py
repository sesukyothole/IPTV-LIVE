#!/usr/bin/env python3
"""
MoveOnJoy Updater (Fast Balanced Mode)
- Per-channel failover + auto-restore (Option A)
- Fast checks (HEAD-first), parallel probing, caching
- Put in scripts/moveonjoy_updater_fast.py
Requires: requests
"""

from pathlib import Path
import re
import time
import subprocess
from datetime import datetime
import requests
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- CONFIG (tweak for speed / safety) ----------
PLAYLIST_CANDIDATES = [
    Path("PrimeVision/us.m3u"),
    Path("IPTV-LIVE/PrimeVision/us.m3u"),
    Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u"),
    Path("us.m3u"),
]

SUB_MIN = 3
SUB_MAX = 50
SUB_RANGE = list(range(SUB_MAX, SUB_MIN - 1, -1))  # fl50 -> fl3

RETRIES = 2                 # fast retries
RETRY_DELAY = 0.6           # small wait between retries
SAMPLE_LIMIT = 3            # sample this many channel lines to evaluate a subdomain (small -> fast)
COOLDOWN_SECONDS = 3600     # 1 hour before pushing subsequent commits (0 disables)
LAST_UPDATE_FILE = Path(".moveonjoy_last_update")

THREAD_WORKERS = 12         # concurrency for probing subdomains/paths
HEAD_TIMEOUT = 3            # seconds for HEAD requests
GET_TIMEOUT = 6             # seconds for GET requests (for small segment check)

# treat these as "special" channels that we prefer to keep on their own working subdomain
SPECIAL_CHANNEL_PATHS = {
    "DISNEY/index.m3u8",
    # add other exact relative paths if needed
}

# Regex to parse MoveOnJoy lines
FL_RE = re.compile(r"https://(fl\d+)\.moveonjoy\.com/([^\s]+)")

# ---------- UTIL / CACHE ----------
_cache = {}  # url -> bool / "playable" result cache for this run

def log(*args, **kwargs):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}]", *args, **kwargs)

def find_playlist():
    for p in PLAYLIST_CANDIDATES:
        if p.exists():
            log("Found playlist at:", p)
            return p
    # recursive fallback
    for p in Path(".").rglob("us.m3u"):
        log("Found playlist via recursive search:", p)
        return p
    return None

def do_head(url, timeout=HEAD_TIMEOUT):
    """HEAD with retries, returns response or None."""
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            return r
        except requests.RequestException:
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return None

def do_get(url, timeout=GET_TIMEOUT):
    """GET with retries, returns response or None."""
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=timeout)
            return r
        except requests.RequestException:
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return None

def fast_check_url_m3u(url):
    """
    Fast balanced check:
    1) HEAD the m3u8; accept 200-399 and content-type containing 'mpegurl' (fast).
    2) If HEAD ambiguous (e.g. 200 but no content-type), try light GET and check for segments.
    Uses per-run cache.
    """
    if url in _cache:
        return _cache[url]

    # HEAD
    r = do_head(url)
    if r and 200 <= r.status_code < 400:
        ct = (r.headers.get("Content-Type") or "").lower()
        if "mpegurl" in ct or "application/vnd.apple.mpegurl" in ct or "vnd.apple.mpegurl" in ct:
            _cache[url] = True
            return True
        # if content-type isn't clear, do a lightweight GET to inspect first lines
        g = do_get(url, timeout=GET_TIMEOUT)
        if g and 200 <= g.status_code < 400:
            text = g.text or ""
            # check for basic segment indicators quickly
            for L in text.splitlines():
                L = L.strip()
                if not L or L.startswith("#"):
                    continue
                if L.endswith(".ts") or L.endswith(".m3u8"):
                    # attempt first segment HEAD/GET quickly if it's absolute or relative
                    if L.startswith("http"):
                        seg_url = L
                    else:
                        seg_url = url.rsplit("/", 1)[0] + "/" + L
                    seg_r = do_head(seg_url) or do_get(seg_url)
                    ok = seg_r is not None and 200 <= seg_r.status_code < 400
                    _cache[url] = ok
                    return ok
    _cache[url] = False
    return False

# ---------- PLAYLIST HELPERS ----------
def read_playlist_lines(path: Path):
    txt = path.read_text(encoding="utf-8")
    lines = txt.splitlines()
    return lines, txt

def write_playlist_lines(path: Path, lines):
    txt = "\n".join(lines)
    if not txt.endswith("\n"):
        txt += "\n"
    path.write_text(txt, encoding="utf-8")

def enumerate_lines_using_subdomain(lines, subdomain):
    for idx, line in enumerate(lines):
        if "http" in line and f"{subdomain}.moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2)

def enumerate_all_fl_lines(lines):
    for idx, line in enumerate(lines):
        if "http" in line and "moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2), m.group(1)

def extract_current_subdomain_from_lines(lines):
    for line in lines:
        m = FL_RE.search(line)
        if m:
            return m.group(1)
    return None

# ---------- FAST LIVENESS & SEARCH (parallel helpers) ----------
def subdomain_alive_any_fast(lines, subdomain, limit=SAMPLE_LIMIT):
    """Fast balanced: sample up to `limit` lines and HEAD-check their m3u8s; return True on first success."""
    checked = 0
    sample = []
    for idx, url, path in enumerate_lines_using_subdomain(lines, subdomain):
        sample.append(url)
        checked += 1
        if checked >= limit:
            break
    if not sample:
        return False

    # run parallel fast checks
    with ThreadPoolExecutor(max_workers=min(len(sample), THREAD_WORKERS)) as ex:
        futures = {ex.submit(fast_check_url_m3u, u): u for u in sample}
        for fut in as_completed(futures):
            ok = fut.result()
            url = futures[fut]
            log = print  # avoid name clash
            if ok:
                print("[FAST] subdomain", subdomain, "alive via", url)
                return True
    return False

def find_fallback_for_path_parallel(path, exclude_sub=None):
    """Find first working flNN for a given path using parallel batches (keeps priority order)."""
    # We'll probe in priority order but in small parallel batches for speed
    batch_size = min(THREAD_WORKERS, 8)
    subs = [f"fl{n}" for n in SUB_RANGE if (exclude_sub is None or f"fl{n}" != exclude_sub)]
    for i in range(0, len(subs), batch_size):
        batch = subs[i:i+batch_size]
        queries = []
        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            for sub in batch:
                url = f"https://{sub}.moveonjoy.com/{path}"
                queries.append(ex.submit(fast_check_url_m3u, url))
            # collect results - return first positive respecting priority
            results = [f.result() for f in queries]
            for sub, ok in zip(batch, results):
                if ok:
                    return sub
    return None

def find_any_fallback_main_fast(lines, exclude_sub=None):
    """Find first subdomain where any channel is playable using parallel probing per subdomain (fast)."""
    # We'll check subdomains in priority order, but probe each subdomain with a small sample set in parallel.
    for n in SUB_RANGE:
        sub = f"fl{n}"
        if exclude_sub and sub == exclude_sub:
            continue
        if subdomain_alive_any_fast(lines, sub, limit=SAMPLE_LIMIT):
            return sub
    return None

# ---------- PER-CHANNEL FAILOVER & AUTO-RESTORE ----------
def per_channel_failover_fast(lines, current_main):
    new_lines = list(lines)
    changed = False
    # collect paths on main
    main_entries = list(enumerate_lines_using_subdomain(lines, current_main))
    if not main_entries:
        return new_lines, False

    # We will check each path's test_url on main using fast_check_url_m3u; for failing paths, find fallback in parallel batches
    to_fix = []
    for idx, full_url, path in main_entries:
        test_url = f"https://{current_main}.moveonjoy.com/{path}"
        if fast_check_url_m3u(test_url):
            continue
        to_fix.append((idx, path))

    if not to_fix:
        return new_lines, False

    # For each path needing fix, try to find fallback (parallel per-path)
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as ex:
        fut_map = {ex.submit(find_fallback_for_path_parallel, path, current_main): (idx, path) for idx, path in to_fix}
        for fut in as_completed(fut_map):
            idx, path = fut_map[fut]
            fallback = fut.result()
            if fallback:
                new_url = f"https://{fallback}.moveonjoy.com/{path}"
                log("Switching path", path, "at line", idx, "to fallback", fallback)
                new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", new_url, new_lines[idx])
                changed = True
            else:
                log("No fallback found for path", path)

    return new_lines, changed

def auto_restore_to_main_fast(lines, current_main):
    new_lines = list(lines)
    changed = False
    # check all fl lines pointing to non-main; if main serves same path now, restore
    tasks = []
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as ex:
        fut_map = {}
        for idx, url, path, sub in enumerate_all_fl_lines(lines):
            if sub == current_main:
                continue
            main_test = f"https://{current_main}.moveonjoy.com/{path}"
            fut = ex.submit(fast_check_url_m3u, main_test)
            fut_map[fut] = (idx, path, main_test)
        for fut in as_completed(fut_map):
            idx, path, main_test = fut_map[fut]
            ok = fut.result()
            if ok:
                log("Restoring", path, "to main", current_main)
                new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", main_test, new_lines[idx])
                changed = True
    return new_lines, changed

# ---------- GIT ----------
def git_commit_and_push_if_changed(path: Path, old_text: str, new_lines, cooldown=COOLDOWN_SECONDS):
    new_text = "\n".join(new_lines)
    if new_text == old_text:
        log("No changes to commit.")
        return False

    now = int(time.time())
    last = 0
    if LAST_UPDATE_FILE.exists():
        try:
            last = int(LAST_UPDATE_FILE.read_text())
        except Exception:
            last = 0

    # write the file (so runner sees update)
    path.write_text(new_text + ("\n" if not new_text.endswith("\n") else ""), encoding="utf-8")
    log("Playlist file updated on disk.")

    if cooldown and (now - last) < cooldown:
        log("Cooldown active — skipping git push.")
        return True

    try:
        subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions"], check=True)
    except Exception as e:
        log("Git config warning:", e)

    try:
        subprocess.run(["git", "add", str(path)], check=True)
        res = subprocess.run(["git", "commit", "-m", f"Auto-update MoveOnJoy subdomains at {datetime.utcnow().isoformat()}"], check=False)
        if res.returncode == 0:
            subprocess.run(["git", "push"], check=True)
            LAST_UPDATE_FILE.write_text(str(now))
            log("Git push completed.")
        else:
            log("Nothing to commit.")
    except subprocess.CalledProcessError as e:
        log("Git operation failed:", e)
    except Exception as e:
        log("Unexpected git error:", e)
    return True

# ---------- MAIN ----------
def main():
    log("MoveOnJoy updater FAST (balanced) starting")
    log("Working dir:", Path(".").resolve())

    p = find_playlist()
    if not p:
        log("ERROR: us.m3u not found. Ensure PrimeVision/us.m3u exists or script run from repo root.")
        sys.exit(1)

    lines, old_text = read_playlist_lines(p)
    current_main = extract_current_subdomain_from_lines(lines)
    if not current_main:
        log("ERROR: no flNN moveonjoy domain found in playlist.")
        sys.exit(1)

    log("Detected current main:", current_main)

    # 1) quick check: is main alive (sample small set)
    main_alive = subdomain_alive_any_fast(lines, current_main, limit=SAMPLE_LIMIT)
    if main_alive:
        log(f"Main {current_main} appears alive (sample check).")
        # try auto-restore to main for channels currently on other subs
        restored_lines, restored_changed = auto_restore_to_main_fast(lines, current_main)
        if restored_changed:
            log("Restored some channels to main; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, restored_lines)
            return
        # check per-channel on main and fix only failing ones
        repaired_lines, repaired_changed = per_channel_failover_fast(lines, current_main)
        if repaired_changed:
            log("Per-channel fallbacks applied; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return
        log("No changes needed.")
        return

    # 2) main appears dead -> try to find fallback main quickly
    log(f"Main {current_main} appears offline (sample failed). Searching fallback main...")
    fallback = find_any_fallback_main_fast(lines, exclude_sub=current_main)
    if not fallback:
        log("No fallback main found quickly. Applying per-channel fallbacks as last resort.")
        repaired_lines, repaired_changed = per_channel_failover_fast(lines, current_main)
        if repaired_changed:
            log("Per-channel fallbacks applied; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return
        log("No changes possible. Exiting.")
        return

    log(f"Found fallback main: {fallback}. Migrating main channels where possible.")
    new_lines = list(lines)
    changed = False
    # try to switch non-special paths to fallback if fallback serves them
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as ex:
        fut_map = {}
        for idx, full_url, path, sub in enumerate_all_fl_lines(lines):
            if path in SPECIAL_CHANNEL_PATHS:
                continue
            # probe fallback path quickly in parallel
            fut = ex.submit(fast_check_url_m3u, f"https://{fallback}.moveonjoy.com/{path}")
            fut_map[fut] = (idx, path)
        for fut in as_completed(fut_map):
            idx, path = fut_map[fut]
            ok = fut.result()
            if ok:
                test_url = f"https://{fallback}.moveonjoy.com/{path}"
                log("Switching path", path, "to fallback", fallback)
                new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", test_url, new_lines[idx])
                changed = True

    if changed:
        log("Writing playlist updates switching main channels to fallback main.")
        git_commit_and_push_if_changed(p, old_text, new_lines)
    else:
        log("Found fallback main but no matching paths found on it; no changes done.")

if __name__ == "__main__":
    main()