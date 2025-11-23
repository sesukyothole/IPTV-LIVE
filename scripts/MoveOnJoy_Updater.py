import asyncio
import aiohttp
import re

# ---- CONFIG ----
M3U_FILE = "PrimeVision/us.m3u"
MAX_FL = 1000
TIMEOUT = 5

# Regex pattern for MoveOnJoy URLs
URL_PATTERN = re.compile(r"(https?://fl)(\d+)(\.mov(e)?onjoy\.com/.*)", re.IGNORECASE)


async def is_online(session, url):
    """
    Proper online/offline validation:
    - GET request (HEAD is unreliable)
    - Requires '#EXTM3U' which must exist in HLS playlists
    """
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return False

            body = await resp.text()

            if "#EXTM3U" in body:
                return True

            return False

    except Exception:
        return False


async def find_working_subdomain(session, channel_path):
    """
    Scan fl1000 → fl1 until a working subdomain is found.
    """
    for fl in range(MAX_FL, 0, -1):
        test_url = f"https://fl{fl}.moveonjoy.com{channel_path}"

        print(f"   → Testing fl{fl} ... ", end="")

        if await is_online(session, test_url):
            print("✔ ONLINE")
            return test_url

        print("✘ offline")

    return None


async def fix_url(session, url):
    match = URL_PATTERN.match(url)
    if not match:
        print(f"SKIP (not MoveOnJoy): {url}")
        return url

    prefix, current_fl, suffix, _ = match.groups()
    current_fl = int(current_fl)
    channel_path = suffix  # "/ACC_NETWORK/index.m3u8"

    print(f"\n🔍 Checking: {url}")

    # Check original flXX first
    if await is_online(session, url):
        print(f"   ✅ ONLINE: fl{current_fl} is working")
        return url

    print(f"   ❌ OFFLINE: fl{current_fl} is down — scanning fl50 → fl1 ...")

    # Find replacement
    working = await find_working_subdomain(session, channel_path)

    if working:
        print(f"   ⚡ REPLACED: fl{current_fl} → {working}")
        return working

    print("   ❌ No working subdomain found — keeping original URL")
    return url


async def process_m3u():
    print(f"📄 Loading: {M3U_FILE}")

    with open(M3U_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modified = False

    async with aiohttp.ClientSession() as session:
        tasks = []

        for index, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith("http") and "moveonjoy.com" in stripped.lower():
                tasks.append((index, fix_url(session, stripped)))

        results = await asyncio.gather(*[task[1] for task in tasks])

        # Write updated URLs back
        for (index, _), new_url in zip(tasks, results):
            if lines[index].strip() != new_url:
                modified = True
                lines[index] = new_url + "\n"

    if modified:
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"\n💾 Saved updates to: {M3U_FILE}")
    else:
        print("\n✨ All MoveOnJoy streams already working — no updates needed")

    print("\n✅ Done!\n")


if __name__ == "__main__":
    asyncio.run(process_m3u())
