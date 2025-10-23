import re
import subprocess
import requests
from datetime import datetime

PLAYLIST_PATH = "IPTV-LIVE/PrimeVision/us.m3u"

SPECIAL_CHANNELS = {
    "DISNEY/index.m3u8",
    "ESPN_U/index.m3u8",
    "HBO_2/index.m3u8"
}

SEARCH_RANGE = range(3, 51)  # fl3 → fl50
TIMEOUT = 3  # Faster check
LOG_PREFIX = "🔎"

def check_stream(url):
    try:
        response = requests.get(url, timeout=TIMEOUT, stream=True)
        ct = response.headers.get("Content-Type", "")
        return response.status_code == 200 and "mpegurl" in ct.lower()
    except:
        return False


def subdomain_alive(subdomain):
    """Check if ANY channel inside playlist works with this domain."""
    test_count = 0
    success = False

    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if f"{subdomain}.moveonjoy.com" in line and "http" in line:
                test_count += 1
                url = line.strip()
                if check_stream(url):
                    print(f"✅ Live stream detected on {subdomain}: {url}")
                    success = True
                    break

                if test_count >= 10:
                    break  # Speed optimization

    if success:
        print(f"✅ {subdomain} is ONLINE")
    else:
        print(f"❌ {subdomain} is OFFLINE")

    return success


def find_working_subdomain(exclude=None):
    """Find the first working subdomain starting from highest fl#."""
    print("🔍 Searching for alternative working MoveOnJoy subdomain...")
    
    for i in reversed(SEARCH_RANGE):  # ✅ Start from fl50 downward
        sub = f"fl{i}"
        if sub == exclude:
            continue
        if subdomain_alive(sub):
            print(f"✅ Found working fallback: {sub}")
            return sub

    print("❌ No working alternative subdomain found!")
    return None


def extract_current_subdomain():
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            match = re.search(r"https://(fl\d+)\.moveonjoy\.com", line)
            if match:
                return match.group(1)
    return None


def update_playlist(current, new):
    with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_url(match):
        url = match.group(0)
        path = match.group(1)
        # Special channels → stay on fallback domain
        return f"https://{current}.moveonjoy.com/{path}"

    # Replace ALL occurrences
    updated = re.sub(
        r"https://fl\d+\.moveonjoy\.com/(.+?\.m3u8)",
        lambda m: (
            f"https://{new}.moveonjoy.com/{m.group(1)}"
            if m.group(1) not in SPECIAL_CHANNELS else m.group(0)
        ),
        content
    )

    with open(PLAYLIST_PATH, "w", encoding="utf-8") as f:
        f.write(updated)


def git_commit_push():
    try:
        subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], check=True)

        subprocess.run(["git", "add", PLAYLIST_PATH], check=True)
        subprocess.run(["git", "commit", "-m",
            f"Auto-update MoveOnJoy subdomains at {datetime.now().isoformat()}"
        ], check=True)
        subprocess.run(["git", "push"], check=True)

        print("✅ Git push completed.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")


def main():
    current = extract_current_subdomain()

    if not current:
        print("❌ No MoveOnJoy subdomain found inside playlist.")
        return

    print(f"{LOG_PREFIX} Current active domain: {current}")

    if subdomain_alive(current):
        print("✅ Current domain is healthy — no update needed.")
        return

    print(f"⚠️ Current domain {current} is offline — searching replacement...")
    new_sub = find_working_subdomain(exclude=current)

    if not new_sub:
        print("❌ No replacement available — keeping current domain.")
        return

    print(f"🔁 Updating playlist → {new_sub}")
    update_playlist(current, new_sub)
    git_commit_push()
    print("✅ Subdomain migration completed successfully ✅")


if __name__ == "__main__":
    main()
