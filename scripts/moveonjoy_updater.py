import os
import re
import requests
import subprocess

# M3U file path
M3U_FILE_PATH = "PrimeVision/us.m3u"

# Range of MoveOnJoy subdomains
START = 2
END = 50

# Segment check settings
NUM_SEGMENTS = 5
TIMEOUT = 5  # seconds per segment


# ------------------- Stream Status Check -------------------

def get_segments(m3u8_url, num_segments=NUM_SEGMENTS):
    """Fetch first few .ts segments from playlist."""
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

def check_stream(url):
    """Return 'online', 'unstable', or 'offline'"""
    segments = get_segments(url)
    if not segments:
        return "offline"
    stable = test_segments(url, segments)
    return "online" if stable else "unstable"


# ------------------- MoveOnJoy Updater -------------------

def find_current_subdomain():
    """Extract current subdomain (flXX) from M3U."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None

def check_domain(subdomain):
    """Quick check if subdomain responds (playlist reachable)."""
    url = f"https://{subdomain}.moveonjoy.com/live/stream.m3u8"
    status = check_stream(url)
    return status != "offline"

def find_next_working_subdomain(current):
    """Find closest working domain if current is offline or unstable."""
    if not current:
        return None
    try:
        current_number = int(re.search(r"\d+", current).group())
    except (AttributeError, ValueError):
        return None

    url = f"https://{current}.moveonjoy.com/live/stream.m3u8"
    stream_status = check_stream(url)
    if stream_status == "online":
        print(f"✅ Current domain {current}.moveonjoy.com is online and stable.")
        return None  # no change needed
    elif stream_status == "unstable":
        print(f"⚠️ Current domain {current}.moveonjoy.com is unstable. Searching alternatives...")
    else:
        print(f"❌ Current domain {current}.moveonjoy.com is offline. Searching alternatives...")

    # Check lower subdomains first
    for i in range(current_number - 1, START - 1, -1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working lower domain: {sub}.moveonjoy.com")
            return sub
    # Then check higher subdomains
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