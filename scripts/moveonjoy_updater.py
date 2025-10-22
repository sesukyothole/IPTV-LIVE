import re
import requests
import time
from pathlib import Path

# Path to your M3U playlist in your GitHub repository
M3U_PATH = Path("PrimeVision/us.m3u")

# Range of subdomains to check (skip fl1 and fl2)
SUBDOMAIN_RANGE = range(50, 2, -1)  # fl50 → fl3 descending

def check_domain(subdomain):
    """Check if a MoveOnJoy subdomain responds at root level (online test)."""
    url = f"https://{subdomain}.moveonjoy.com/"
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        if r.status_code < 400:
            print(f"✅ {subdomain}.moveonjoy.com is online.")
            return True
        else:
            print(f"⚠️ {subdomain}.moveonjoy.com returned {r.status_code}.")
    except requests.RequestException:
        print(f"❌ {subdomain}.moveonjoy.com is offline or unstable.")
    return False


def find_working_subdomain():
    """Find a working MoveOnJoy subdomain from fl3–fl50."""
    print("🔍 Searching for available MoveOnJoy redirect (fl3–fl50)...")
    for i in SUBDOMAIN_RANGE:
        subdomain = f"fl{i}"
        if check_domain(subdomain):
            return subdomain
        time.sleep(0.5)
    return None


def find_current_subdomain(content):
    """Find the current subdomain used in the M3U playlist."""
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None


def update_playlist(current, new):
    """Replace old subdomain with a new working one."""
    content = M3U_PATH.read_text(encoding="utf-8")
    updated_content = re.sub(current, new, content)
    M3U_PATH.write_text(updated_content, encoding="utf-8")
    print(f"📝 Updated playlist: {current} → {new}")


def main():
    print("🚀 MoveOnJoy Auto-Updater Initialized")

    content = M3U_PATH.read_text(encoding="utf-8")
    current = find_current_subdomain(content)

    if not current:
        print("❌ Could not find any MoveOnJoy domain in playlist.")
        return

    print(f"🔍 Checking if current domain {current}.moveonjoy.com is online...")

    # Double-check if current subdomain is reachable
    if check_domain(current):
        print(f"✅ Current domain {current}.moveonjoy.com is still working.")
        print("ℹ️ No updates were needed.")
        return

    print(f"❌ Current domain {current}.moveonjoy.com is offline. Searching alternatives...")
    new = find_working_subdomain()

    if not new:
        print("❌ No working subdomain found from fl3–fl50.")
        print("ℹ️ No updates were needed.")
        return

    update_playlist(current, new)
    print(f"✅ Updated playlist successfully with {new}.moveonjoy.com!")


if __name__ == "__main__":
    main()