#!/usr/bin/env python3
"""
MoveOnJoy Updater v4.1 — Per-Channel Smart Failover + Auto-Restore (Option A)
- Place in: scripts/moveonjoy_updater.py
- Playlist expected: PrimeVision/us.m3u (auto-detected)
- Requirements: requests
"""

from pathlib import Path
import re
import time
import subprocess
from datetime import datetime
import requests
import sys

# ---------- CONFIG ----------
PLAYLIST_CANDIDATES = [
    Path("PrimeVision/us.m3u"),
    Path("IPTV-LIVE/PrimeVision/us.m3u"),
    Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u"),
    Path("us.m3u"),
]

SUB_MIN = 3
SUB_MAX = 50
SUB_RANGE = list(range(SUB_MAX, SUB_MIN - 1, -1))  # fl50 -> fl3

RETRIES = 3
RETRY_DELAY = 1  # seconds
SAMPLE_LIMIT = 10  # when sampling lines to test a domain
COOLDOWN_SECONDS = 3600  # 1 hour between commits (set 0 to disable)
LAST_UPDATE_FILE = Path(".moveonjoy_last_update")

# Paths we treat as "special" (prefer to keep on their own working subdomain)
SPECIAL_CHANNEL_PATHS = {
    "DISNEY/index.m3u8",
    # add other exact relative paths here if needed
}

# Regex to parse MoveOnJoy lines like: https://fl25.moveonjoy.com/PATH/index.m3u8
FL_RE = re.compile(r"https://(fl\d+)\.moveonjoy\.com/([^\s]+)")

# ---------- UTILITIES ----------

def log(*args, **kwargs):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}]", *args, **kwargs)

def find_playlist():
    """Return Path to us.m3u or None"""
    for p in PLAYLIST_CANDIDATES:
        if p.exists():
            log("Found playlist at:", p)
            return p
    # recursive search fallback
    for p in Path(".").rglob("us.m3u"):
        log("Found playlist via recursive search:", p)
        return p
    return None

def http_get(url, timeout=6, stream=False):
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=timeout, stream=stream)
            return r
        except requests.RequestException as e:
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return None

def check_playlist_has_segments(text):
    """Basic heuristic if m3u8 contains segments or variant playlists."""
    if not text:
        return False
    for L in text.splitlines():
        L = L.strip()
        if L and not L.startswith("#") and (L.endswith(".ts") or L.endswith(".m3u8")):
            return True
    return False

def check_stream_playable(m3u8_url):
    """Return True if playlist reachable and the first referenced segment is reachable."""
    r = http_get(m3u8_url, timeout=6)
    if not r or r.status_code >= 400:
        return False
    text = r.text
    if not check_playlist_has_segments(text):
        # some servers don't list segments; treat as not playable
        return False
    # find first candidate segment or nested m3u8
    for L in text.splitlines():
        L = L.strip()
        if not L or L.startswith("#"):
            continue
        # candidate
        if L.startswith("http"):
            seg_url = L
        else:
            seg_url = m3u8_url.rsplit("/", 1)[0] + "/" + L
        seg_r = http_get(seg_url, timeout=6)
        return (seg_r is not None) and (seg_r.status_code < 400)
    return False

# ---------- PLAYLIST HELPERS ----------

def read_playlist_lines(m3u_path):
    text = m3u_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    return lines, text

def write_playlist_lines(m3u_path, new_lines):
    txt = "\n".join(new_lines)
    # ensure final newline
    if not txt.endswith("\n"):
        txt += "\n"
    m3u_path.write_text(txt, encoding="utf-8")

def enumerate_lines_using_subdomain(lines, subdomain):
    """Yield (idx, full_url, relative_path) lines that reference this subdomain."""
    for idx, line in enumerate(lines):
        if "http" in line and f"{subdomain}.moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2)

def enumerate_all_fl_lines(lines):
    """Yield (idx, full_url, relative_path, subdomain) for all moveonjoy lines"""
    for idx, line in enumerate(lines):
        if "http" in line and "moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2), m.group(1)

def extract_current_subdomain_from_lines(lines):
    """Return the first flNN in the playlist lines, or None."""
    for line in lines:
        m = FL_RE.search(line)
        if m:
            return m.group(1)
    return None

# ---------- LIVENESS & SEARCH ----------

def subdomain_alive_any(lines, subdomain, limit=SAMPLE_LIMIT):
    """
    Consider subdomain alive if ANY channel on that subdomain is playable.
    Sample up to 'limit' channels for speed.
    """
    checked = 0
    for idx, url, path in enumerate_lines_using_subdomain(lines, subdomain):
        checked += 1
        log(f"Testing {url} ...")
        if check_stream_playable(url):
            log(" -> playable (subdomain alive).")
            return True
        else:
            log(" -> not playable.")
        if checked >= limit:
            break
    return False

def find_fallback_for_path(path, exclude_sub=None):
    """Find first flNN (50->3) where the given path is playable."""
    for n in SUB_RANGE:
        sub = f"fl{n}"
        if exclude_sub and sub == exclude_sub:
            continue
        url = f"https://{sub}.moveonjoy.com/{path}"
        log("Trying", url)
        if check_stream_playable(url):
            log(" -> path works on", sub)
            return sub
    return None

def find_any_fallback_main(lines, exclude_sub=None):
    """Find first subdomain where at least one channel is playable (50->3)."""
    for n in SUB_RANGE:
        sub = f"fl{n}"
        if exclude_sub and sub == exclude_sub:
            continue
        log("Probing subdomain", sub)
        if subdomain_alive_any(lines, sub, limit=SAMPLE_LIMIT):
            return sub
    return None

# ---------- PER-CHANNEL FAILOVER & AUTO-RESTORE ----------

def per_channel_failover(lines, current_main):
    """
    For each line on current_main, if that path is not playable on current_main,
    switch that line to a working flNN for that path.
    Returns (new_lines, changed_flag)
    """
    new_lines = list(lines)
    changed = False

    for idx, full_url, path in enumerate_lines_using_subdomain(lines, current_main):
        # path may already be on non-main (skip)
        # test path on main
        test_url = f"https://{current_main}.moveonjoy.com/{path}"
        log("Checking path on main:", test_url)
        if check_stream_playable(test_url):
            log(" -> works on main; keep it.")
            continue

        # Path failing on main; search per-path fallback
        fallback = find_fallback_for_path(path, exclude_sub=current_main)
        if fallback:
            new_url = f"https://{fallback}.moveonjoy.com/{path}"
            log(f"Switching line index {idx} path {path} to fallback {fallback}")
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", new_url, new_lines[idx])
            changed = True
        else:
            log(f"No fallback found for path {path}; leaving as-is")

    return new_lines, changed

def auto_restore_to_main(lines, current_main):
    """
    For lines that currently point to other flNN, if current_main now serves the same path,
    restore those lines back to current_main.
    Returns (new_lines, changed_flag)
    """
    new_lines = list(lines)
    changed = False
    for idx, full_url, path, sub in enumerate_all_fl_lines(lines):
        if sub == current_main:
            continue
        main_test = f"https://{current_main}.moveonjoy.com/{path}"
        log("Checking if main now serves", path)
        if check_stream_playable(main_test):
            log(f"Restoring {path} to main {current_main}")
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", main_test, new_lines[idx])
            changed = True
    return new_lines, changed

# ---------- GIT & WRITE ----------

def git_commit_and_push_if_changed(m3u_path: Path, old_text: str, new_lines, cooldown=COOLDOWN_SECONDS):
    new_text = "\n".join(new_lines)
    if new_text == old_text:
        log("No textual changes to playlist — nothing to commit.")
        return False

    # cooldown check
    now = int(time.time())
    last = 0
    if LAST_UPDATE_FILE.exists():
        try:
            last = int(LAST_UPDATE_FILE.read_text())
        except Exception:
            last = 0

    # write file regardless (so the runner and any downstream steps see updated playlist)
    m3u_path.write_text(new_text + ("\n" if not new_text.endswith("\n") else ""), encoding="utf-8")
    log("Playlist file updated on disk.")

    if cooldown and (now - last) < cooldown:
        log(f"Cooldown active ({now-last}s since last push) — skipping git push.")
        return True

    # configure git (best-effort)
    try:
        subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions"], check=True)
    except Exception as e:
        log("Git config warning:", e)

    try:
        subprocess.run(["git", "add", str(m3u_path)], check=True)
        res = subprocess.run(["git", "commit", "-m", f"Auto-update MoveOnJoy subdomains at {datetime.utcnow().isoformat()}"], check=False)
        if res.returncode == 0:
            subprocess.run(["git", "push"], check=True)
            LAST_UPDATE_FILE.write_text(str(now))
            log("Git push completed.")
        else:
            log("Nothing to commit (git returned no changes).")
    except subprocess.CalledProcessError as e:
        log("Git operation failed:", e)
    except Exception as e:
        log("Unexpected git error:", e)

    return True

# ---------- MAIN FLOW ----------

def main():
    log("MoveOnJoy Updater v4.1 starting")
    # debug working dir + list top-level files (helps GH Actions)
    log("Working dir:", Path(".").resolve())
    log("Top-level entries:")
    for itm in sorted(Path(".").iterdir()):
        log(" -", itm)

    p = find_playlist()
    if not p:
        log("ERROR: us.m3u not found. Ensure playlist exists at PrimeVision/us.m3u or run from repo root.")
        sys.exit(1)

    lines, old_text = read_playlist_lines(p)
    current_main = extract_current_subdomain_from_lines(lines)
    if not current_main:
        log("ERROR: no flNN moveonjoy domain found in playlist.")
        sys.exit(1)

    log("Detected main subdomain:", current_main)

    # 1) If any channel on current_main is playable -> main considered alive
    main_alive = subdomain_alive_any(lines, current_main, limit=SAMPLE_LIMIT)

    if main_alive:
        log(f"Main {current_main} appears alive (at least one playable channel).")
        # 1a) Try to restore channels (on other flXX) back to main if their path works on main
        restored_lines, restored_changed = auto_restore_to_main(lines, current_main)
        if restored_changed:
            log("Restored channels back to main; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, restored_lines)
            return

        # 1b) Check channels on main that are individually offline -> per-channel fallback
        repaired_lines, repaired_changed = per_channel_failover(lines, current_main)
        if repaired_changed:
            log("Applied per-channel fallbacks for some main channels; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return

        log("All good — no changes needed.")
        return

    # 2) main appears dead (no playable channel found) -> find a fallback main
    log(f"Main {current_main} appears offline (no playable channels). Searching fallback main...")
    fallback_main = find_any_fallback_main(lines, exclude_sub=current_main)
    if not fallback_main:
        log("No fallback main found. Attempting per-channel fallbacks (may partially recover channels).")
        repaired_lines, repaired_changed = per_channel_failover(lines, current_main)
        if repaired_changed:
            log("Per-channel fallbacks applied; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return
        log("No changes possible. Exiting.")
        return

    log(f"Found fallback main: {fallback_main}. Migrating main channels where possible.")
    new_lines = list(lines)
    changed = False
    for idx, url, path, sub in enumerate_all_fl_lines(lines):
        if path in SPECIAL_CHANNEL_PATHS:
            continue
        # attempt to move this path to fallback_main only if that path works there
        test_url = f"https://{fallback_main}.moveonjoy.com/{path}"
        log("Testing fallback path:", test_url)
        if check_stream_playable(test_url):
            log(f" -> path works on fallback; switching line idx {idx} to {fallback_main}")
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", test_url, new_lines[idx])
            changed = True

    if changed:
        log("Writing playlist updates switching main channels to fallback main.")
        git_commit_and_push_if_changed(p, old_text, new_lines)
    else:
        log("Found fallback main but no matching paths available on it; no changes performed.")

if __name__ == "__main__":
    main()