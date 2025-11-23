import asyncio
import aiohttp
import re

M3U_FILE = "PrimeVision/us.m3u"  # Update with your actual file path
MAX_FL = 50
TIMEOUT = 5

URL_PATTERN = re.compile(r"(https?://fl)(\d+)(\.movonjoy\.com/.*)")

async def is_online(session, url):
    try:
        async with session.head(url, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except:
        return False

async def fix_url(session, url):
    match = URL_PATTERN.match(url)
    if not match:
        return url

    if await is_online(session, url):
        print(f"✅ Online: {url}")
        return url

    prefix, _, suffix = match.groups()
    for i in range(1, MAX_FL + 1):
        new_url = f"{prefix}{i}{suffix}"
        if await is_online(session, new_url):
            print(f"⚡ Replaced: {url} -> {new_url}")
            return new_url

    print(f"❌ No working subdomain found for {url}")
    return url

async def process_m3u():
    with open(M3U_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, line in enumerate(lines):
            line = line.strip()
            if line.startswith("http") and "movonjoy.com" in line:
                tasks.append((idx, fix_url(session, line)))

        resolved = await asyncio.gather(*[task[1] for task in tasks])

        for (idx, _), new_url in zip(tasks, resolved):
            lines[idx] = new_url + "\n"

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\n✅ M3U file '{M3U_FILE}' updated successfully!")

if __name__ == "__main__":
    asyncio.run(process_m3u())