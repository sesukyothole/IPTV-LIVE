import requests
import re
import time
import subprocess
from datetime import datetime

PLAYLIST_PATH = "playlist.m3u"
MAIN_SUBDOMAIN = "fl25"  # Will auto-update if dead
RANGE = range(3, 51)  # fl3 – fl50

SPECIAL_CHANNELS = {
    "DISNEY": "DISNEY/index.m3u8",
    "ESPN_U": "ESPN_U/index.m3u8",
    "HBO_2": "HBO_2/index.m3u8"
}

LOG_PREFIX = "🛰 MoveOnJoy:"

def check_stream(url):
    """Returns True only if playlist + TS segment is healthy."""
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return False
        
        # Find TS segments
        match = re.search(r"(.*\.ts)", r.text)
        if not match:
            return False
        
        ts_url = url.rsplit("/", 1)[0] + "/" + match.group(1)
        ts = requests.get(ts_url, timeout=5)
        return ts.status_code == 200
    except:
        return False

def find_working_subdomain(channel):
    print(f"{LOG_PREFIX} Searching new working subdomain for {channel}...")

    for i in RANGE:
        test_sub = f"fl{i}"
        url = f"https://{test_sub}.moveonjoy.com/{SPECIAL_CHANNELS[channel]}"
        if check_stream(url):
            print(f"✅ Found working: {url}")
            return test_sub
        
    print(f"❌ No working subdomain found for {channel}...")
    return None

def subdomain_alive(subdomain):
    """Check if MAIN_SUBDOMAIN still usable using multiple samples."""
    print(f"{LOG_PREFIX} Checking status of {subdomain}...")
    ok_count = 0

    for channel, path in SPECIAL_CHANNELS.items():
        url = f"https://{subdomain}.moveonjoy.com/{path}"
        if check_stream(url):
            ok_count += 1
    
    return ok_count >= 2  # At least 2 working = acceptable

def update_playlist(new_subdomain=None):
    updated = False

    with open(PLAYLIST_PATH, "r", encoding="utf-8") as file:
        lines = file.read()

    for channel, path in SPECIAL_CHANNELS.items():
        old_pattern = rf"https://fl\d+\.moveonjoy\.com/{path}"
        new_link = f"https://{new_subdomain}.moveonjoy.com/{path}"
        if re.search(old_pattern, lines):
            lines = re.sub(old_pattern, new_link, lines)
            print(f"🔁 Updated {channel} → {new_subdomain}")
            updated = True

    if updated:
        with open(PLAYLIST_PATH, "w", encoding="utf-8") as file:
            file.write(lines)
        print("✅ Playlist update written!")
    else:
        print("ℹ️ Playlist already up to date.")

    return updated

def git_push():
    try:
        subprocess.run(["git", "add", PLAYLIST_PATH])
        commit_msg = f"Auto-update MoveOnJoy at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        subprocess.run(["git", "commit", "-m", commit_msg])
        subprocess.run(["git", "push"])
        print("🚀 Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push failed: {e}")

def main():
    global MAIN_SUBDOMAIN

    print("━━━━━━━━━━━━━━━━━━")
    print(f"{LOG_PREFIX} Started at {datetime.now()}")
    print("━━━━━━━━━━━━━━━━━━")

    print(f"{LOG_PREFIX} Current subdomain = {MAIN_SUBDOMAIN}")

    if not subdomain_alive(MAIN_SUBDOMAIN):
        print("❌ Current main subdomain is offline")
        
        # Use DISNEY as master reference to select replacement
        new_sub = find_working_subdomain("DISNEY")
        if new_sub:
            print(f"🔄 Changing main subdomain → {new_sub}")
            MAIN_SUBDOMAIN = new_sub
            changed = update_playlist(new_sub)
            if changed:
                git_push()
        else:
            print("⚠️ No alternative subdomain found!")
    else:
        print("✅ Main subdomain is online! Nothing to update.")

    print("━━━━━━━━━━━━━━━━━━")
    print("✅ Script completed ✅")

if __name__ == "__main__":
    main()