import re
import requests
from pathlib import Path

# --- CONFIG ---
CHECK_RANGE = range(1, 51)  # fl1 through fl50
OLD_DOMAIN_PATTERN = r"mov\d+\.moveonjoy\.(?:com|xyz)"
PLAYLIST_PATH = Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u")

print("🔍 Searching for available MoveOnJoy redirect (fl1–fl50)...")

NEW_DOMAIN = None
WORKING_FL = None

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0 Safari/537.36"
}

for i in CHECK_RANGE:
    test_url = f"https://fl{i}.moveonjoy.com/"
    try:
        resp = requests.get(test_url, allow_redirects=True, timeout=6, headers=headers)
        # Check final redirected URL first
        match_redirect = re.search(r"(mov\d+\.moveonjoy\.(?:com|xyz))", resp.url)
        # Then check the page content if no redirect
        match_body = re.search(r"(mov\d+\.moveonjoy\.(?:com|xyz))", resp.text)
        match = match_redirect or match_body
        if match:
            NEW_DOMAIN = match.group(1)
            WORKING_FL = f"fl{i}.moveonjoy.com"
            print(f"✅ Working: {WORKING_FL} → {NEW_DOMAIN}")
            break
        else:
            print(f"⚙️ Tried {test_url} — no redirect detected.")
    except requests.RequestException:
        continue

if not NEW_DOMAIN:
    print("❌ Could not find any working MoveOnJoy redirect from fl1–fl50.")
    exit(0)

# --- STEP 2: Update playlist ---
if not PLAYLIST_PATH.exists():
    print(f"⚠️ Playlist not found at: {PLAYLIST_PATH}")
    exit(0)

print(f"🧩 Updating playlist: {PLAYLIST_PATH}")

content = PLAYLIST_PATH.read_text(encoding="utf-8")
matches = re.findall(OLD_DOMAIN_PATTERN, content)

if matches:
    old_domain = matches[0]
    updated = re.sub(OLD_DOMAIN_PATTERN, NEW_DOMAIN, content)
    PLAYLIST_PATH.write_text(updated, encoding="utf-8")
    print(f"✅ Replaced '{old_domain}' → '{NEW_DOMAIN}' in {PLAYLIST_PATH}")
else:
    print("ℹ️ No MoveOnJoy links found or already up-to-date.")

print(f"🎉 Update complete. Using redirect from {WORKING_FL}")