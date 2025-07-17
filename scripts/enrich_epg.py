import os
import aiohttp
import asyncio
import xml.etree.ElementTree as ET

# Manual TMDb overrides
MANUAL_ID_OVERRIDES = {
    "Jessie": {"type": "tv", "id": 38974},
    "Big City Greens": {"type": "tv", "id": 80587},
    "Kiff": {"type": "tv", "id": 127706},
    "Zombies": {"type": "movie", "id": 483980},
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id": 585},
    "The Incredibles": {"type": "movie", "id": 9806},
    "SpongeBob SquarePants": {"type": "tv", "id": 387},
    "Peppa Pig": {"type": "tv", "id": 12225},
    "PAW Patrol": {"type": "tv", "id": 57532},
    "Rubble & Crew": {"type": "tv", "id": 214875},
    "Gabby's Dollhouse": {"type": "tv", "id": 111474},
    "black-ish": {"type": "tv", "id": 61381},
    "Phineas and Ferb": {"type": "tv", "id": 1877},
    "Win or Lose": {"type": "tv", "id": 114500},
    "Friends": {"type": "tv", "id": 1668},
    "Primos": {"type": "tv", "id": 204139},
    "DuckTales": {"type": "tv", "id": 72350},
    "Mulan": {"type": "movie", "id": 337401},
    "Moana": {"type": "movie", "id": 277834},
    "Modern Family": {"type": "tv", "id": 1421},
    "Henry Danger": {"type": "tv", "id": 61852},
    "The Really Loud House": {"type": "tv", "id": 211779}
}

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"

HEADERS = {"Authorization": f"Bearer {TMDB_API_KEY}"}


async def fetch_tmdb_data(session, title):
    if title in MANUAL_ID_OVERRIDES:
        media = MANUAL_ID_OVERRIDES[title]
        url = f"{TMDB_BASE}/{media['type']}/{media['id']}?language=en-US&append_to_response=images"
    else:
        search_url = f"{TMDB_BASE}/search/multi?query={title}&language=en-US"
        async with session.get(search_url, headers=HEADERS) as resp:
            result = await resp.json()
            if not result["results"]:
                return None
            item = result["results"][0]
            media_type = item["media_type"]
            tmdb_id = item["id"]
            url = f"{TMDB_BASE}/{media_type}/{tmdb_id}?language=en-US&append_to_response=images"

    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return None
        return await resp.json()


def get_landscape_image(data):
    backdrops = data.get("images", {}).get("backdrops", [])
    for img in backdrops:
        if img.get("iso_639_1") == "en":
            return TMDB_IMAGE_BASE + img["file_path"]
    if backdrops:
        return TMDB_IMAGE_BASE + backdrops[0]["file_path"]
    return None


async def enrich_channel_icon(session, channel):
    display_name = channel.find("display-name")
    if display_name is None:
        return

    title = display_name.text
    data = await fetch_tmdb_data(session, title)
    if data is None:
        return

    image_url = get_landscape_image(data)
    if image_url is None:
        return

    icon = channel.find("icon")
    if icon is not None:
        channel.remove(icon)

    ET.SubElement(channel, "icon", attrib={"src": image_url})


async def process_epg(epg_path, output_path):
    tree = ET.parse(epg_path)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [
            enrich_channel_icon(session, channel)
            for channel in root.findall("channel")
        ]
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python enrich_epg.py <input.xml> <output.xml>")
        exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    asyncio.run(process_epg(input_file, output_file))