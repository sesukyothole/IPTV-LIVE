import re
import requests
from pathlib import Path

# --- CONFIGURATION ---
# Redirect link that points to the current active MoveOnJoy domain
FL_URL = "https://fl.moveonjoy.com/"
OLD_DOMAIN_PATTERN = r"mov\d+\.moveonjoy\.(?:com|xyz)"

# Path to your specific M3U playlist
PLAYLIST_PATH = Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u")

# --- STEP 1: Detect current working domain from the FL redirect ---
print("🔍 Checking current MoveOnJoy redirect...")

try:
    response = requests.get(FL_URL, allow_redirects=True, timeout=10)
    final_url = response.url
    match = re.search(r"(mov\d+\.moveonjoy\.(?:com|xyz))", final_url)
    if not match:
        raise ValueError("No valid MoveOnJoy domain found in redirect URL.")
    NEW_DOMAIN = match.group(1)
    print(f"✅ Found new domain: {NEW_DOMAIN}")
except Exception as e:
    print(f"❌ Error fetching new domain: {e}")
    exit(1)

# --- STEP 2: Replace old domain in the specific M3U file ---
if not PLAYLIST_PATH.exists():
    print(f"❌ Playlist not found at: {PLAYLIST_PATH}")
    exit(1)

print(f"🧩 Updating playlist: {PLAYLIST_PATH}")

content = PLAYLIST_PATH.read_text(encoding="utf-8")

if re.search(OLD_DOMAIN_PATTERN, content):
    updated = re.sub(OLD_DOMAIN_PATTERN, NEW_DOMAIN, content)
    PLAYLIST_PATH.write_text(updated, encoding="utf-8")
    print(f"✅ Updated domain in {PLAYLIST_PATH}")
else:
    print("ℹ️ No MoveOnJoy links found or already up-to-date.")

print("🎉 Task complete.")
