import asyncio
import aiohttp
import re

M3U_FILE = "PrimeVision/us.m3u"  # Change this to your M3U file path
MAX_FL = 50  # Maximum MoveOnJoy subdomain number
TIMEOUT = 5  # Timeout for HTTP requests in seconds

# Regex to detect MoveOnJoy URLs with fl subdomains
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
        return url  # Not a MoveOnJoy URL
    
    # Check if current URL is online
    if await is_online(session, url):
        return url  # Already online, no change needed

    prefix, _, suffix = match.groups()

    # Rotate through fl1 → fl50
    for i in range(1, MAX_FL + 1):
        new_url = f"{prefix}{i}{suffix}"
        if await is_online(session, new_url):
            return new_url

    return url  # No working subdomain found, return original

async def process_m3u():
    # Read playlist
    with open(M3U_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, line in enumerate(lines):
            line = line.strip()
            if line.startswith("http") and "movonjoy.com" in line:
                tasks.append((idx, fix_url(session, line)))

        # Resolve only offline URLs asynchronously
        resolved = await asyncio.gather(*[task[1] for task in tasks])

        # Replace lines with resolved URLs
        for (idx, _), new_url in zip(tasks, resolved):
            lines[idx] = new_url + "\n"

    # Write back to the same file
    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

if __name__ == "__main__":
    asyncio.run(process_m3u())