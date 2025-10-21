import os
import re
import requests
import subprocess

# Your M3U file path in the repo
M3U_FILE_PATH = "PrimeVision/us.m3u"

# Range of MoveOnJoy subdomains to test
START = 2
END = 50

# Timeout for each request (seconds)
TIMEOUT = 3

def find_working_subdomain():
    print(f"🔍 Searching for available MoveOnJoy redirect (fl{START}–fl{END})...")
    for i in range(START, END + 1):
        subdomain = f"fl{i}"
        url = f"https://{subdomain}.moveonjoy.com/"
        try:
            # Try HEAD first
            response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code >= 400:
                # If HEAD fails, try GET (some servers block HEAD)
                response = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
            
            if response.status_code < 400:
                print(f"✅ Found working MoveOnJoy domain: {subdomain}.moveonjoy.com ({response.status_code})")
                return subdomain
            else:
                print(f"⚙️ Tried {url} — status {response.status_code}.")
        except requests.RequestException:
            print(f"⚙️ Tried {url} — connection failed.")
    print(f"❌ Could not find any working MoveOnJoy redirect from fl{START}–fl{END}.")
    return None


def update_m3u(subdomain):
    if not os.path.exists(M3U_FILE_PATH):
        print(f"❌ Playlist not found at {M3U_FILE_PATH}")
        return False

    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace all old MoveOnJoy subdomains (flX.moveonjoy.com)
    pattern = r"https://fl\d+\.moveonjoy\.com"
    new_url = f"https://{subdomain}.moveonjoy.com"
    new_content, count = re.subn(pattern, new_url, content)

    if count == 0:
        print("ℹ️ No MoveOnJoy links found in playlist.")
        return False

    with open(M3U_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Updated {count} link(s) to {subdomain}.moveonjoy.com in {M3U_FILE_PATH}")
    return True


def commit_changes():
    """Commit and push changes if running in GitHub Actions."""
    if os.getenv("GITHUB_ACTIONS"):
        print("💾 Committing changes to repository...")
        subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
        subprocess.run(["git", "add", M3U_FILE_PATH], check=False)
        subprocess.run(["git", "commit", "-m", "Auto-update MoveOnJoy subdomain"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("✅ Commit pushed successfully.")


def main():
    working_subdomain = find_working_subdomain()
    if working_subdomain and update_m3u(working_subdomain):
        commit_changes()
    else:
        print("⚠️ No playlist changes made.")


if __name__ == "__main__":
    main()