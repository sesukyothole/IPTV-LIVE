import asyncio
import aiohttp
import re

# ---- CONFIG ----
M3U_FILE = "PrimeVision/us.m3u"   # <- Change if needed
MAX_FL = 50
TIMEOUT = 5

# Matches https://flXX.moveonjoy.com/xxxx
URL_PATTERN = re.compile(r"(https?://fl)(\d+)(\.mov(e)?onjoy\.com/.*)", re.IGNORECASE)


async def is_online(session, url):
    """
    Accurate online/offline check:
    - Uses GET (HEAD gives false positives)
    - Validates the response contains #EXTM3U (required for real HLS streams)
    """
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return False

            body = await resp.text()

            # Real HLS playlist always contains "#EXTM3U"
            if "#EXTM3U" in body:
                return True

            return False

    except Exception:
        return False


async def fix_url(session, url):
    match = URL_PATTERN.match(url)
    if not match:
        print(f"SKIP (not MoveOnJoy): {url}")
        return url

    prefix, current_fl, suffix, _ = match.groups()
    current_fl = int(current_fl)

    print(f"\n🔍 Checking: {url}")

    # Test original link first
    if await is_online(session, url):
        print(f"   ✅ ONLINE: fl{current_fl} is working")
        return url

    print(f"   ❌ OFFLINE: fl{current_fl} is down, scanning for alternatives...")

    # Try fl1 → fl50
    for fl in range(1, MAX_FL + 1):
        new_url = f"{prefix}{fl}{suffix}"

        print(f"   → Testing fl{fl} ... ", end="")

        if await is_online(session, new_url):
            print("✔ ONLINE")
            print(f"   ⚡ REPLACED: fl{current_fl} → fl{fl}")
            return new_url
        else:
            print("✘ offline")

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

        # Run all checks concurrently
        results = await asyncio.gather(*[task[1] for task in tasks])

        # Apply replacements
        for (index, _), new_url in zip(tasks, results):
            if lines[index].strip() != new_url:
                modified = True
                lines[index] = new_url + "\n"

    if modified:
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"\n💾 Saved updates to: {M3U_FILE}")
    else:
        print("\n✨ All MoveOnJoy streams are already online — no changes made")

    print("\n✅ Done!\n")


if __name__ == "__main__":
    asyncio.run(process_m3u())