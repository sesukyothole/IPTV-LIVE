import asyncio
import aiohttp
import re

# ---- CONFIG ----
M3U_FILE = "PrimeVision/us.m3u"
MAX_FL = 100          # Default max scan range
TIMEOUT = 5

# Regex pattern for MoveOnJoy URLs
URL_PATTERN = re.compile(r"(https?://fl)(\d+)(\.mov(e)?onjoy\.com/.*)", re.IGNORECASE)


async def is_online(session, url):
    """
    Proper online/offline validation:
    - GET request only (HEAD gives false positives)
    - Checks for valid HLS playlist (#EXTM3U)
    """
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return False

            body = await resp.text()

            # Valid HLS playlist indicator
            return "#EXTM3U" in body

    except Exception:
        return False


async def find_working_subdomain(session, channel_path, current_fl):
    """
    Scan flMAX → fl1.
    If none work, force fallback to fl1.
    """
    effective_max = max(MAX_FL, current_fl)  # auto-expand range
    fallback_url = f"https://fl1.moveonjoy.com{channel_path}"

    found_working = None

    for fl in range(effective_max, 0, -1):
        test_url = f"https://fl{fl}.moveonjoy.com{channel_path}"

        print(f"   → Testing fl{fl} ... ", end="")

        if await is_online(session, test_url):
            print("✔ ONLINE")
            found_working = test_url
            break

        print("✘ offline")

    if found_working:
        return found_working

    # FORCE fallback → fl1
    print("   ⚠️ All subdomains offline — forcing fallback → fl1")
    return fallback_url


async def fix_url(session, url):
    match = URL_PATTERN.match(url)
    if not match:
        print(f"SKIP (not MoveOnJoy): {url}")
        return url

    prefix, current_fl, suffix, _ = match.groups()
    current_fl = int(current_fl)
    channel_path = suffix  # e.g. "/ACC_NETWORK/index.m3u8"

    print(f"\n🔍 Checking: {url}")

    # Check original flXX first
    if await is_online(session, url):
        print(f"   ✅ ONLINE: fl{current_fl} is working")
        return url

    print(f"   ❌ OFFLINE: fl{current_fl} is down — scanning fl{max(current_fl, MAX_FL)} → fl1 ...")

    # Find alternative
    working_url = await find_working_subdomain(session, channel_path, current_fl)

    if working_url != url:
        print(f"   ⚡ REPLACED: fl{current_fl} → {working_url}")

    return working_url


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

        # Apply URL replacements
        for (index, _), new_url in zip(tasks, results):
            if lines[index].strip() != new_url:
                modified = True
                lines[index] = new_url + "\n"

    if modified:
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"\n💾 Saved updates to: {M3U_FILE}")
    else:
        print("\n✨ All MoveOnJoy URLs are already online — no updates needed")

    print("\n✅ Done!\n")


if __name__ == "__main__":
    asyncio.run(process_m3u())