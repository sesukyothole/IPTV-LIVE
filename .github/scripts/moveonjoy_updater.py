import re
import requests
from pathlib import Path

FL_URL = "https://fl.moveonjoy.com/"
OLD_DOMAIN_PATTERN = r"mov\d+\.moveonjoy\.(?:com|xyz)"
PLAYLIST_PATH = Path("gtvservices5/IPTV-LIVE/PrimeVision/us.m3u")

print("🔍 Checking current MoveOnJoy redirect...")

NEW_DOMAIN = None

try:
    response = requests.get(FL_URL, allow_redirects=True, timeout=10)
    final_url = response.url
    match = re.search(r"(mov\d+\.moveonjoy\.(?:com|xyz))", final_url)
    if match:
        NEW_DOMAIN = match.group(1)
        print(f"✅ Found new domain: {NEW_DOMAIN}")
    else:
        print("⚠️ No valid MoveOnJoy domain found in redirect URL.")
except Exception as e:
    print(f"⚠️ Error fetching domain from {FL_URL}: {e}")

# Stop here if no domain found
if not NEW_DOMAIN:
    print("❌ Could not determine new MoveOnJoy domain. No changes made.")
    exit(0)

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
    print("ℹ️ Playlist already up-to-date or no MoveOnJoy links found.")

print("🎉 Script completed successfully.")