#!/usr/bin/env python3
"""
MoveOnJoy Auto-Updater v4.0 — per-channel failover + auto-restore (Option A)
- Finds us.m3u in the repository (no hard-coded path)
- Checks current main flXX subdomain by scanning channels that use it
- If main is dead, finds a new working subdomain and moves main channels there
- If individual channels on main are down, moves only those channels to a working subdomain for that path
- When main returns, restores channels back to main (if path works there)
- Safe git commit/push with check for actual changes and optional cooldown
Requirements: requests
"""

import re
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
import requests

# ---------- CONFIG ----------
SUBDOMAIN_MIN = 3
SUBDOMAIN_MAX = 50
SUBDOMAIN_RANGE = list(range(SUBDOMAIN_MAX, SUBDOMAIN_MIN - 1, -1))  # 50 -> 3

RETRIES = 3
RETRY_DELAY = 1  # seconds between retries
SAMPLE_LIMIT = 10  # number of channel lines to test when checking a subdomain
COOLDOWN_SECONDS = 3600  # optional cooldown for git pushes; set 0 to disable
LAST_UPDATE_FILE = Path(".moveonjoy_last_update")  # stored in repo root

# treat these as "special" channels that we prefer to keep on their own working subdomain
SPECIAL_CHANNEL_PATHS = {
    "DISNEY/index.m3u8",
    # you can add others if you want per-channel preference
}

# ---------- UTILITIES ----------

def find_us_m3u():
    """Find 'us.m3u' anywhere in the repo (first match)."""
    for p in Path(".").rglob("us.m3u"):
        return p
    # fallback common paths
    candidates = [
        Path("IPTV-LIVE/PrimeVision/us.m3u"),
        Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u"),
        Path("PrimeVision/us.m3u"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def http_get(url, stream=False, timeout=6):
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=timeout, stream=stream)
            return r
        except requests.RequestException:
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return None

def url_is_ok(url):
    """Lightweight check: GET (not HEAD) with retries; returns True if HTTP 200."""
    r = http_get(url, stream=False, timeout=6)
    return (r is not None) and (r.status_code < 400)

def stream_has_segments(m3u8_text):
    """Return True if playlist contains .ts or .m3u8 segments (basic sanity)."""
    if not m3u8_text:
        return False
    lines = m3u8_text.splitlines()
    for L in lines:
        if L.strip().endswith(".ts") or L.strip().endswith(".m3u8"):
            return True
    return False

def check_stream_playable(m3u8_url):
    """Check playlist reachable and has segments that are reachable (fast check)."""
    r = http_get(m3u8_url, stream=False, timeout=6)
    if not r or r.status_code >= 400:
        return False
    text = r.text
    if not stream_has_segments(text):
        # playlist may be a redirect or not list segments; still accept 200 for some cases
        return False
    # try first segment if relative
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(".ts") or line.endswith(".m3u8"):
            if line.startswith("http"):
                seg_url = line
            else:
                seg_url = m3u8_url.rsplit("/", 1)[0] + "/" + line
            seg_r = http_get(seg_url, stream=False, timeout=5)
            if seg_r and seg_r.status_code < 400:
                return True
            else:
                return False
    return False

# ---------- PLAYLIST PARSING ----------

def parse_playlist_lines(m3u_path):
    """Return list of lines (keeps order)."""
    text = m3u_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    return lines, text

def write_playlist(m3u_path, new_lines):
    new_text = "\n".join(new_lines) + ("\n" if new_lines and not new_lines[-1].endswith("\n") else "")
    m3u_path.write_text(new_text, encoding="utf-8")

# ---------- SUBDOMAIN & PATH HELPERS ----------

FL_RE = re.compile(r"https://(fl\d+)\.moveonjoy\.com/([^\s]+)")

def lines_using_subdomain(lines, subdomain):
    """Yield (idx, url, path) for each url line that references the subdomain."""
    for idx, line in enumerate(lines):
        if "http" in line and f"{subdomain}.moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2)

def extract_current_main(lines):
    """Return first flNN found in playlist or None."""
    for line in lines:
        m = FL_RE.search(line)
        if m:
            return m.group(1)
    return None

from urllib.parse import urlparse

def extract_current_subdomain(lines):
    """
    Extract the first flNN subdomain found in playlist lines.
    Example: https://fl25.moveonjoy.com/ACC_NETWORK/index.m3u8 -> fl25
    """
    for line in lines:
        # look for https://flXX.moveonjoy.com/
        m = re.search(r"https://(fl\d+)\.moveonjoy\.com/", line)
        if m:
            return m.group(1)
    return None
# ---------- LIVENESS CHECKS ----------

def subdomain_alive_by_any_channel(lines, subdomain, limit=SAMPLE_LIMIT):
    """
    Consider subdomain alive if ANY channel on that subdomain is playable.
    We sample up to 'limit' lines for speed.
    """
    checked = 0
    for idx, url, path in lines_using_subdomain(lines, subdomain):
        checked += 1
        if check_stream_playable(url):
            # success: at least one playable channel present
            return True
        if checked >= limit:
            break
    return False

def subdomain_online_fraction(lines, subdomain, sample_paths=None):
    """
    Optionally check fraction of sample_paths (list of relative paths) on that subdomain.
    Returns fraction_online (0.0-1.0)
    """
    if not sample_paths:
        return 0.0
    online = 0
    for p in sample_paths:
        url = f"https://{subdomain}.moveonjoy.com/{p}"
        if check_stream_playable(url):
            online += 1
    return online / len(sample_paths)

# ---------- SEARCHING FALLBACKS ----------

def find_working_subdomain_for_path(path, exclude_sub=None):
    """Find first subdomain (50->3) where https://flXX.moveonjoy.com/{path} is playable."""
    for i in SUBDOMAIN_RANGE:
        sub = f"fl{i}"
        if exclude_sub and sub == exclude_sub:
            continue
        url = f"https://{sub}.moveonjoy.com/{path}"
        if check_stream_playable(url):
            return sub
    return None

def find_working_subdomain_for_any(lines, exclude_sub=None):
    """Find first subdomain where at least one channel is playable (scans each fl)."""
    for i in SUBDOMAIN_RANGE:
        sub = f"fl{i}"
        if exclude_sub and sub == exclude_sub:
            continue
        if subdomain_alive_by_any_channel(lines, sub):
            return sub
    return None

# ---------- PER-CHANNEL FAILOVER & AUTO-RESTORE ----------

def per_channel_failover(lines, current_main):
    """
    For each line that uses current_main, if that specific path is not playable on current_main,
    find a working flXX for that path and replace the line with the working fl.
    Returns (new_lines, changed_flag)
    """
    new_lines = list(lines)  # copy
    changed = False

    for idx, url, path in lines_using_subdomain(lines, current_main):
        # skip special channels if they already have their own working host different from main
        if path in SPECIAL_CHANNEL_PATHS:
            # current line might already point to non-main; keep that
            # but if it points to main and it's offline, we will search fallback
            pass

        # check if the path works on current_main
        test_url = f"https://{current_main}.moveonjoy.com/{path}"
        if check_stream_playable(test_url):
            # path works on main — no change
            continue

        # path fails on main; find fallback for this path
        fallback = find_working_subdomain_for_path(path, exclude_sub=current_main)
        if fallback:
            new_url = f"https://{fallback}.moveonjoy.com/{path}"
            print(f"⚠️ Path offline on {current_main}: {path} → switching this channel to {fallback}")
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", new_url, new_lines[idx])
            changed = True
        else:
            print(f"❌ No fallback found for path {path} (on {current_main}) — leaving as-is")

    return new_lines, changed

def auto_restore_to_main(lines, current_main):
    """
    If current_main is alive, attempt to restore channels that are on other flXX back to main,
    but only if the exact path works again on main.
    Returns (new_lines, changed_flag)
    """
    new_lines = list(lines)
    changed = False
    for idx, url, path in enumerate_all_fl_lines(lines):
        m = FL_RE.search(url)
        if not m:
            continue
        sub = m.group(1)
        if sub == current_main:
            continue
        # check if current_main now serves same path
        main_try = f"https://{current_main}.moveonjoy.com/{m.group(2)}"
        if check_stream_playable(main_try):
            # replace line
            new_url = main_try
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", new_url, new_lines[idx])
            print(f"🔁 Restored {m.group(2)} back to main {current_main}")
            changed = True
    return new_lines, changed

def enumerate_all_fl_lines(lines):
    """Yield (idx, url, path) for all lines that match flNN."""
    for idx, line in enumerate(lines):
        if "http" in line and "moveonjoy.com" in line:
            m = FL_RE.search(line)
            if m:
                yield idx, m.group(0), m.group(2)

# ---------- GIT ----------

def git_commit_and_push_if_changed(m3u_path, old_text, new_lines, cooldown_seconds=COOLDOWN_SECONDS):
    new_text = "\n".join(new_lines)
    if new_text == old_text:
        print("ℹ️ No textual changes to playlist — nothing to commit.")
        return False

    # cooldown check
    now = int(time.time())
    last = 0
    try:
        if LAST_UPDATE_FILE.exists():
            last = int(LAST_UPDATE_FILE.read_text())
    except Exception:
        last = 0

    if cooldown_seconds and (now - last) < cooldown_seconds:
        print("⏱ Cooldown active — skipping git commit/push.")
        # still write file so the runner sees updated playlist
        m3u_path.write_text(new_text, encoding="utf-8")
        return True  # file changed but not pushed

    # write file
    m3u_path.write_text(new_text, encoding="utf-8")

    try:
        subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions"], check=True)
    except Exception as e:
        print("⚠️ Git config failed (non-fatal):", e)

    try:
        subprocess.run(["git", "add", str(m3u_path)], check=True)
        res = subprocess.run(["git", "commit", "-m", f"Auto-update MoveOnJoy subdomains at {datetime.utcnow().isoformat()}"], check=False)
        if res.returncode == 0:
            subprocess.run(["git", "push"], check=True)
            LAST_UPDATE_FILE.write_text(str(now))
            print("✅ Changes committed and pushed.")
        else:
            print("ℹ️ Nothing to commit (git returned no changes).")
    except subprocess.CalledProcessError as e:
        print("❌ Git operation failed:", e)
    except Exception as e:
        print("❌ Unexpected git error:", e)
    return True

# ---------- MAIN FLOW ----------

def main():
    p = find_us_m3u()
    if not p:
        print("❌ Could not find us.m3u in repo (searched recursively).")
        return

    print(f"🔎 Using playlist file: {p}")

    lines, old_text = parse_playlist_lines(p)
    current_main = extract_current_subdomain(lines)
    if not current_main:
        print("❌ No flNN moveonjoy domain found in playlist.")
        return

    print(f"🔎 Detected main subdomain: {current_main}")

    # 1) If ANY channel on current_main is playable -> consider main alive
    main_alive = subdomain_alive_by_any_channel(lines, current_main, limit=SAMPLE_LIMIT)

    if main_alive:
        print(f"✅ Main {current_main} appears alive (at least one working channel).")
        # 1a) perform per-channel fix for channels on other subdomains: try to restore them back to main
        restored_lines, restored_changed = auto_restore_to_main(lines, current_main)
        if restored_changed:
            print("🔁 Restored some channels back to main; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, restored_lines)
            return
        # 1b) also, check channels *on* main that are individually offline and move them to a fallback (per-channel)
        repaired_lines, repaired_changed = per_channel_failover(lines, current_main)
        if repaired_changed:
            print("🔧 Some channels on main were failing and moved to fallbacks; committing (respecting cooldown).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return
        print("ℹ️ All good — no changes needed.")
        return

    # 2) main is not alive (no playable channel found) -> find fallback main
    print(f"⚠️ Main {current_main} appears offline (no playable channels found). Searching for a replacement main...")
    fallback_main = find_working_subdomain_for_any(lines, exclude_sub=current_main)
    if not fallback_main:
        print("❌ No fallback main subdomain found. Attempting per-channel fallbacks instead.")
        # try per-channel fallbacks (still may help)
        repaired_lines, repaired_changed = per_channel_failover(lines, current_main)
        if repaired_changed:
            print("🔧 Per-channel fallbacks applied (no global fallback).")
            git_commit_and_push_if_changed(p, old_text, repaired_lines)
            return
        print("❌ No changes possible; aborting.")
        return

    print(f"🔁 Found new main subdomain: {fallback_main} — migrating main channels to {fallback_main}")

    # Replace main for all non-special channels if fallback_main has those paths working
    new_lines = list(lines)
    changed_any = False
    for idx, url, path in enumerate_all_fl_lines(lines):
        m = FL_RE.search(url)
        if not m:
            continue
        sub = m.group(1)
        # skip special channels (we preserve their own handling)
        if path in SPECIAL_CHANNEL_PATHS:
            continue
        # attempt to switch line to fallback_main only if fallback has that path working
        test_url = f"https://{fallback_main}.moveonjoy.com/{path}"
        if check_stream_playable(test_url):
            new_url = test_url
            new_lines[idx] = re.sub(r"https://fl\d+\.moveonjoy\.com/[^\s]+", new_url, new_lines[idx])
            changed_any = True

    if changed_any:
        print("📝 Written playlist updates switching main channels to fallback main.")
        git_commit_and_push_if_changed(p, old_text, new_lines)
    else:
        print("⚠️ Found fallback main but no individual path matched there — nothing changed.")

if __name__ == "__main__":
    main()