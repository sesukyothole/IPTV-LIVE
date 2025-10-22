import re
import requests
import subprocess
import time
from pathlib import Path

# ----------------- CONFIG -----------------
M3U_PATH = Path("PrimeVision/us.m3u")
SUBDOMAIN_RANGE = range(50, 2, -1)  # fl50 → fl3
SPECIAL_CHANNELS = {
    "DISNEY/index.m3u8": "Disney Channel USA"
}
RETRIES = 3
RETRY_DELAY = 1  # seconds

# ----------------- HELPER FUNCTIONS -----------------

def check_url(url, retries=RETRIES):
    """Check if a full URL is online, with retries."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 400:
                if attempt > 1:
                    print(f"✅ URL recovered on attempt {attempt}: {url}")
                return True
        except requests.RequestException:
            print(f"⚠️ Attempt {attempt} failed for {url}")
        time.sleep(RETRY_DELAY)
    return False


def find_working_subdomain_for_path(path):
    """Find the first working subdomain for a specific path."""
    for i in SUBDOMAIN_RANGE:
        subdomain = f"fl{i}"
        url = f"https://{subdomain}.moveonjoy.com/{path}"
        if check_url(url):
            return subdomain
    return None


def update_playlist_line(line, new_subdomain, path):
    """Replace the subdomain in this line only."""
    pattern = rf"https://fl\d+\.moveonjoy\.com/{re.escape(path)}"
    return re.sub(pattern, f"https://{new_subdomain}.moveonjoy.com/{path}", line)


def find_current_main_subdomain(content):
    """Detect the current main domain in playlist."""
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None


def git_commit_and_push(file_path, message):
    """Commit changes and push to GitHub."""
    try:
        subprocess.run(["git", "add", str(file_path)], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print(f"🚀 Changes committed and pushed: {message}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")


# ----------------- MAIN -----------------

def main():
    print("🚀 MoveOnJoy Auto-Updater Initialized")
    content = M3U_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    updated_lines = []

    # Detect main subdomain
    current_main = find_current_main_subdomain(content)
    if not current_main:
        print("❌ No MoveOnJoy domain found in playlist.")
        return

    print(f"🔍 Checking main subdomain {current_main}.moveonjoy.com...")
    main_online = check_url(f"https://{current_main}.moveonjoy.com/")
    if not main_online:
        print(f"❌ Main subdomain {current_main} is offline. Searching alternatives...")
        new_main = None
        for i in SUBDOMAIN_RANGE:
            sub = f"fl{i}"
            if check_url(f"https://{sub}.moveonjoy.com/"):
                new_main = sub
                print(f"✅ Found new main subdomain: {sub}")
                break
        if new_main:
            print(f"📝 Updating main subdomain {current_main} → {new_main}")
            current_main = new_main
        else:
            print("❌ No working main subdomain found. Keeping old main.")

    # Process each line
    playlist_changed = False
    for line in lines:
        updated_line = line
        is_special = False

        # Special channels first
        for path, name in SPECIAL_CHANNELS.items():
            if path in line:
                is_special = True
                print(f"🔍 Checking special channel {name}")
                if not check_url(line):
                    print(f"❌ {name} offline. Searching working subdomain...")
                    new_sub = find_working_subdomain_for_path(path)
                    if new_sub:
                        updated_line = update_playlist_line(line, new_sub, path)
                        print(f"✅ Updated {name} → {new_sub}.moveonjoy.com")
                        playlist_changed = True
                    else:
                        print(f"❌ No working subdomain found for {name}. Leaving old URL.")
                break  # Stop checking other special channels for this line

        # Replace main subdomain if this line is not a special channel
        if not is_special and current_main:
            new_line = re.sub(r"https://fl\d+\.moveonjoy\.com", f"https://{current_main}.moveonjoy.com", updated_line)
            if new_line != updated_line:
                playlist_changed = True
                updated_line = new_line

        updated_lines.append(updated_line)

    # Save updated playlist if anything changed
    if playlist_changed:
        M3U_PATH.write_text("\n".join(updated_lines), encoding="utf-8")
        print("📝 Playlist update completed.")

        # Commit and push changes to GitHub
        git_commit_and_push(M3U_PATH, f"Auto-update MoveOnJoy subdomains at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("ℹ️ No changes needed in playlist.")


if __name__ == "__main__":
    main()