import os
import re
import requests
import subprocess

# M3U file path
M3U_FILE_PATH = "PrimeVision/us.m3u"

# Range of MoveOnJoy subdomains to test
START = 2
END = 50

# Timeout (seconds)
TIMEOUT = 3


def check_domain(subdomain):
    """Return True if the MoveOnJoy subdomain responds successfully."""
    url = f"https://{subdomain}.moveonjoy.com/"
    try:
        response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            response = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        return response.status_code < 400
    except requests.RequestException:
        return False


def find_current_subdomain():
    """Extract the current subdomain (e.g. fl25) from the M3U playlist."""
    if not os.path.exists(M3U_FILE_PATH):
        return None
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"https://(fl\d+)\.moveonjoy\.com", content)
    return match.group(1) if match else None


def find_next_working_subdomain(current):
    """Find the next working MoveOnJoy domain — lower first, then higher."""
    if not current:
        print("⚠️ No current subdomain found in playlist.")
        return None

    try:
        current_number = int(re.search(r"\d+", current).group())
    except (AttributeError, ValueError):
        return None

    print(f"🔍 Checking if current domain {current}.moveonjoy.com is online...")
    if check_domain(current):
        print(f"✅ Current domain {current}.moveonjoy.com is still working.")
        return None  # No change needed

    print(f"❌ {current}.moveonjoy.com is offline. Searching for alternatives...")

    # Check lower subdomains first
    for i in range(current_number - 1, START - 1, -1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working lower domain: {sub}.moveonjoy.com")
            return sub

    # If no lower found, check higher ones
    for i in range(current_number + 1, END + 1):
        sub = f"fl{i}"
        if check_domain(sub):
            print(f"✅ Found working higher domain: {sub}.moveonjoy.com")
            return sub

    print(f"❌ No working subdomain found from fl{START}–fl{END}.")
    return None


def update_m3u(subdomain):
    """Replace old MoveOnJoy subdomain with the new one in the playlist."""
    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

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
    """Commit and push changes if running inside GitHub Actions."""
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