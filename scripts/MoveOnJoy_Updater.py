import asyncio
import aiohttp
import re

# CHANGE THIS to match your actual file:
M3U_FILE = "PrimeVision/us.m3u"

MAX_FL = 50
TIMEOUT = 5

# Matches: https://fl3.movonjoy.com/xxxxxx
URL_PATTERN = re.compile(r"(https?://fl)(\d+)(\.movonjoy\.com/.*)")

async def is_online(session, url):
    """Returns True if the URL responds with status 200."""
    try:
        async with session.head(url, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False

async def fix_url(session, url):
    """Check URL, log status, and replace only if offline."""
    match = URL_PATTERN.match(url)
    if not match:
        print(f"SKIP (not MoveOnJoy): {url}")
        return url

    prefix, current_fl, suffix = match.groups()
    current_fl = int(current_fl)

    print(f"\n🔍 Checking: {url}")

    # Check if the current subdomain is online
    if await is_online(session, url):
        print(f"   ✅ ONLINE: fl{current_fl} is working")
        return url

    print(f"   ❌ OFFLINE: fl{current_fl} is down, searching for replacement...")

    # Try all subdomains from fl1 to fl50
    for i in range(1, MAX_FL + 1):
        new_url = f"{prefix}{i}{suffix}"
        print(f"   → Testing fl{i} ... ", end="")

        if await is_online(session, new_url):
            print("✔ ONLINE")
            print(f"   ⚡ REPLACED: fl{current_fl} ➜ fl{i}")
            return new_url
        else:
            print("✘ offline")

    print("   ❌ No working subdomain found — keeping original")
    return url


async def process_m3u():
    print(f"📄 Loading playlist: {M3U_FILE}")

    with open(M3U_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modified = False

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, line in enumerate(lines):
            line = line.strip()
            # Only check MoveOnJoy URLs
            if line.startswith("http") and "movonjoy.com" in line:
                tasks.append((idx, fix_url(session, line)))

        # Run checks in parallel
        results = await asyncio.gather(*[task[1] for task in tasks])

        # Apply updated URLs
        for (idx, _), new_url in zip(tasks, results):
            if lines[idx].strip() != new_url:
                modified = True
                lines[idx] = new_url + "\n"

    # Write only if something changed
    if modified:
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"\n💾 Saved updates to {M3U_FILE}")
    else:
        print("\n✨ No updates needed — all MoveOnJoy streams online")

    print("\n✅ Finished!\n")


if __name__ == "__main__":
    asyncio.run(process_m3u())