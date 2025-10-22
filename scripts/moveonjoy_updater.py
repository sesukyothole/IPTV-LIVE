import re
import requests
import time
from pathlib import Path

M3U_PATH = Path("PrimeVision/us.m3u")
SUBDOMAIN_RANGE = range(50, 2, -1)  # fl50 → fl3

SPECIAL_CHANNELS = {
    "DISNEY/index.m3u8": "Disney Channel USA"
}

def check_domain(subdomain, retries=3):
    """Check if a MoveOnJoy subdomain responds reliably."""
    url = f"https://{subdomain}.moveonjoy.com/"
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=5, allow_redirects=True)
            if r.status_code < 400:
                if attempt > 1:
                    print(f"✅ {subdomain}.moveonjoy.com recovered on attempt {attempt}.")
                else:
                    print(f"✅ {subdomain}.moveonjoy.com is online.")
                return True
        except requests.RequestException:
            print(f"⚠️ Attempt {attempt}: {subdomain}.moveonjoy.com not responding...")
        time.sleep(1)
    print(f"❌ {subdomain}.moveonjoy.com is unstable/offline after {retries} tries.")
    return False


def find_working_subdomain():
    """Find a stable MoveOnJoy domain (fl50–fl3)."""
    print("🔍 Searching for available MoveOnJoy redirect (fl3–fl50)...")
    for i in SUBDOMAIN_RANGE:
        subdomain = f"fl{i}"
        if check_domain(subdomain):
            return subdomain
    return None


def find_current_subdomain(content):
    """Detect the current domain in playlist."""
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None


def update_playlist(current, new):
    """Replace the domain inside the M3U."""
    content = M3U_PATH.read_text(encoding="utf-8")
    updated = re.sub(current, new, content)
    M3U_PATH.write_text(updated, encoding="utf-8")
    print(f"📝 Updated playlist: {current} → {new}")


def main():
    print("🚀 MoveOnJoy Auto-Updater Initialized")
    content = M3U_PATH.read_text(encoding="utf-8")
    current = find_current_subdomain(content)

    if not current:
        print("❌ Could not find any MoveOnJoy domain in playlist.")
        return

    print(f"🔍 Checking if current domain {current}.moveonjoy.com is stable...")
    if check_domain(current):
        print(f"✅ Current domain {current}.moveonjoy.com is still stable.")
        print("ℹ️ No updates were needed.")
        return

    print(f"❌ Current domain {current}.moveonjoy.com is offline. Searching alternatives...")
    new = find_working_subdomain()

    if not new:
        print("❌ No stable subdomain found from fl3–fl50.")
        print("ℹ️ No updates were made.")
        return

    update_playlist(current, new)
    print(f"✅ Updated playlist successfully with {new}.moveonjoy.com!")


if __name__ == "__main__":
    main()