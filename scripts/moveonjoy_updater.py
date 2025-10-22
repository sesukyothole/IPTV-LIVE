import os
import re
import requests
import subprocess

# M3U playlist path
M3U_FILE_PATH = "PrimeVision/us.m3u"

# MoveOnJoy subdomain range
START = 2
END = 50

# Segment check settings
NUM_SEGMENTS = 5
TIMEOUT = 5  # seconds per request


# ------------------- Stream Status Check -------------------

def get_segments(m3u8_url, num_segments=NUM_SEGMENTS):
    """Fetch first few .ts segments from playlist, if present."""
    try:
        r = requests.get(m3u8_url, timeout=TIMEOUT)
        r.raise_for_status()
        lines = r.text.splitlines()
        segments = [line for line in lines if line.endswith(".ts")]
        return segments[:num_segments]
    except requests.RequestException:
        return []

def test_segments(base_url, segments):
    """Check if segments can be downloaded."""
    if not segments:
        return False
    stable = True
    for seg in segments:
        if not seg.startswith("http"):
            url = base_url.rsplit("/", 1)[0] + "/" + seg
        else:
            url = seg
        try:
            r = requests.head(url, timeout=TIMEOUT)
            if r.status_code >= 400:
                stable = False
        except requests.RequestException:
            stable = False
    return stable

def check_stream_status(subdomain):
    """Return 'online', 'unstable', or 'offline' for a subdomain."""
    root_url = f"https://{subdomain}.moveonjoy.com/"
    try:
        r = requests.head(root_url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            # fallback GET request
            r = requests.get(root_url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            return "offline"
    except requests.RequestException:
        return "offline"

    # Try checking segments if M3U is present
    m3u_url = find_playlist_url(subdomain)
    if not m3u_url:
        return "online"  # no playlist, root works → consider online

    segments = get_segments(m3u_url)
    if not segments:
        return "offline"  # playlist missing or unreachable

    stable = test_segments(m3u_url, segments)
    return "online" if stable else "unstable"


def find_playlist_url(subdomain):
    """Return playlist URL from M3U file for the subdomain."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # Extract playlist URL that contains this subdomain
    match = re.search(rf"https://{subdomain}\.moveonjoy\.com[^\s]*\.m3u8", content)
    return match.group(0) if match else None


# ------------------- MoveOnJoy Updater -------------------

def find_current_subdomain():
    """Extract current subdomain (flXX) from the M3U playlist."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None


def check_domain(subdomain):
    """Quick check if subdomain root responds."""
    status = check_stream_status(subdomain)
    return status != "offline"


def find_next_working_subdomain(current):
    """Find closest working subdomain if current is offline or unstable."""
    if not current:
        return None
    try:
        current_number = int(re.search(r"\d+", current).group())
    except (AttributeError, ValueError):
        return None

    # Check current domain status
    status = check_stream_status(current)
    if status == "online":
        print(f"✅ Current domain {current}.moveonjoy.com is online and stable.")
        return None
    elif status == "unstable":
        print(f"⚠️ Current domain {current}.moveonjoy.com is unstable. Searching alternatives...")
    else:
        print(f"❌ Current domain {current}.moveonjoy.com is offline. Searching alternatives...")

    # Lower subdomains first
    for i in range(current_number - 1, START - 1, -1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working lower domain: {sub}.moveonjoy.com")
            return sub

    # Then higher subdomains
    for i in range(current_number + 1, END + 1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working higher domain: {sub}.moveonjoy.com")
            return sub

    print(f"❌ No working subdomain found from fl{START}–fl{END}.")
    return None


def update_m3u(subdomain):
    """Replace old subdomain with new one in M3U."""
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r"https://fl\d+\.moveonjoy\.com"
    new_url = f"https://{subdomain}.moveonjoy.com"
    if new_url in content:
        print(f"ℹ️ Playlist already uses {new_url}. No update needed.")
        return False
    new_content, count = re.subn(pattern, new_url, content)
    if count == 0:
        print("ℹ️ No MoveOnJoy links found in playlist.")
        return False
    with open(M3U_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✅ Updated {count} link(s) to {new_url} in {M3U_FILE_PATH}")
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
    current = find_current_subdomain()
    next_sub = find_next_working_subdomain(current)
    if next_sub and update_m3u(next_sub):
        commit_changes()
    else:
        print("ℹ️ No updates were needed.")


if __name__ == "__main__":
    main()