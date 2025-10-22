import os
import re
import time
import requests
import subprocess

# M3U playlist location
M3U_FILE_PATH = "PrimeVision/us.m3u"

# MoveOnJoy domain range
START = 5
END = 50

# Request settings
TIMEOUT = 5
RETRY_DELAY = 3  # seconds before re-check


# ------------------- Domain/Stream Checkers -------------------

def check_domain_once(subdomain):
    """Check root response for a single attempt."""
    url = f"https://{subdomain}.moveonjoy.com/"
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code < 400:
            return True
        # fallback: GET
        r = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code < 400
    except requests.RequestException:
        return False


def check_domain(subdomain):
    """Double-check the domain's online status to reduce false positives."""
    if not check_domain_once(subdomain):
        return False
    # Wait a bit before confirming
    time.sleep(RETRY_DELAY)
    return check_domain_once(subdomain)


def get_segments(m3u8_url, limit=5):
    """Return first few .ts segments if playlist is accessible."""
    try:
        r = requests.get(m3u8_url, timeout=TIMEOUT)
        r.raise_for_status()
        lines = r.text.splitlines()
        return [line for line in lines if line.endswith(".ts")][:limit]
    except requests.RequestException:
        return []


def check_segments(base_url, segments):
    """Check if segments are downloadable (for stability)."""
    if not segments:
        return False
    for seg in segments:
        if not seg.startswith("http"):
            url = base_url.rsplit("/", 1)[0] + "/" + seg
        else:
            url = seg
        try:
            r = requests.head(url, timeout=TIMEOUT)
            if r.status_code >= 400:
                return False
        except requests.RequestException:
            return False
    return True


def check_stream_status(subdomain, playlist_url=None):
    """
    Return one of:
    - 'online'    → reachable + stable segments
    - 'unstable'  → reachable but segments partially fail
    - 'offline'   → unreachable
    """
    if not check_domain(subdomain):
        return "offline"

    if not playlist_url:
        return "online"

    segments = get_segments(playlist_url)
    if not segments:
        return "unstable"

    stable = check_segments(playlist_url, segments)
    return "online" if stable else "unstable"


# ------------------- M3U Updater -------------------

def find_current_subdomain():
    """Extract current flXX from playlist."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", text)
    return match.group(1) if match else None


def find_playlist_url(subdomain):
    """Get .m3u8 URL from the playlist that matches this subdomain."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, encoding="utf-8") as f:
        text = f.read()
    match = re.search(rf"https://{subdomain}\.moveonjoy\.com[^\s]*\.m3u8", text)
    return match.group(0) if match else None


def update_m3u(new_subdomain):
    """Replace old MoveOnJoy subdomain with new one."""
    with open(M3U_FILE_PATH, encoding="utf-8") as f:
        content = f.read()
    pattern = r"https://fl\d+\.moveonjoy\.com"
    new_url = f"https://{new_subdomain}.moveonjoy.com"
    if new_url in content:
        print(f"ℹ️ Playlist already uses {new_url}.")
        return False
    new_content, count = re.subn(pattern, new_url, content)
    if count == 0:
        print("ℹ️ No MoveOnJoy links found.")
        return False
    with open(M3U_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✅ Updated {count} link(s) to {new_url}.")
    return True


def commit_changes():
    """Commit & push changes (for GitHub Actions)."""
    if os.getenv("GITHUB_ACTIONS"):
        print("💾 Committing changes...")
        subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
        subprocess.run(["git", "add", M3U_FILE_PATH], check=False)
        subprocess.run(["git", "commit", "-m", "Auto-update MoveOnJoy subdomain"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("✅ Commit pushed.")


# ------------------- Domain Selector -------------------

def find_next_working_subdomain(current):
    """Search for the next available subdomain if current is unstable/offline."""
    if not current:
        return None
    try:
        current_num = int(re.search(r"\d+", current).group())
    except Exception:
        return None

    playlist_url = find_playlist_url(current)
    status = check_stream_status(current, playlist_url)

    if status == "online":
        print(f"✅ {current}.moveonjoy.com is online and stable.")
        return None
    elif status == "unstable":
        print(f"⚠️ {current}.moveonjoy.com is unstable — searching for a replacement...")
    else:
        print(f"❌ {current}.moveonjoy.com is offline — searching for alternatives...")

    # Check lower subdomains first
    for i in range(current_num - 1, START - 1, -1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working lower domain: {sub}.moveonjoy.com")
            return sub

    # Then check higher subdomains
    for i in range(current_num + 1, END + 1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working higher domain: {sub}.moveonjoy.com")
            return sub

    print(f"❌ No working subdomain found from fl{START}–fl{END}.")
    return None


# ------------------- Main Routine -------------------

def main():
    current = find_current_subdomain()
    if not current:
        print("⚠️ No MoveOnJoy domain found in playlist.")
        return

    next_sub = find_next_working_subdomain(current)
    if next_sub and update_m3u(next_sub):
        commit_changes()
    else:
        print("ℹ️ No updates needed.")


if __name__ == "__main__":
    main()
