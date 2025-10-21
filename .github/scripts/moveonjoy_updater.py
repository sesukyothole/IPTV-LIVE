import os
import re
import requests

# Your M3U file path in the repo
M3U_FILE_PATH = "PrimeVision/us.m3u"

# Range of MoveOnJoy subdomains to test
START = 1
END = 50

# Timeout for each request (seconds)
TIMEOUT = 3

def find_working_subdomain():
    print("🔍 Searching for available MoveOnJoy redirect (fl2–fl50)...")
    for i in range(START, END + 1):
        subdomain = f"fl2{i}"
        url = f"https://{subdomain}.moveonjoy.com/"
        try:
            response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code < 400:  # any 2xx or 3xx means it's online
                print(f"✅ Found working MoveOnJoy domain: {subdomain}.moveonjoy.com ({response.status_code})")
                return subdomain
            else:
                print(f"⚙️ Tried {url} — status {response.status_code}.")
        except requests.RequestException:
            print(f"⚙️ Tried {url} — connection failed.")
    print("❌ Could not find any working MoveOnJoy redirect from fl2–fl50.")
    return None

def update_m3u(subdomain):
    if not os.path.exists(M3U_FILE_PATH):
        print(f"❌ Playlist not found at {M3U_FILE_PATH}")
        return False

    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace all old MoveOnJoy subdomains (flX.moveonjoy.com) with the new one
    new_content = re.sub(r"https://fl\d+\.moveonjoy\.com", f"https://{subdomain}.moveonjoy.com", content)

    if content == new_content:
        print("ℹ️ No subdomain changes detected in playlist.")
        return False

    with open(M3U_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Updated MoveOnJoy subdomain to {subdomain}.moveonjoy.com in {M3U_FILE_PATH}")
    return True

def main():
    working_subdomain = find_working_subdomain()
    if working_subdomain:
        update_m3u(working_subdomain)
    else:
        print("⚠️ No available subdomain found. Playlist not updated.")

if __name__ == "__main__":
    main()