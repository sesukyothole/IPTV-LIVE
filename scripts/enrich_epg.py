import asyncio
import aiohttp
import xml.etree.ElementTree as ET

# === TMDb API Key ===
TMDB_API_KEY = "your_tmdb_api_key_here"  # <-- replace this with your actual key

# === Manual TMDb Overrides ===
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


async def fetch_tmdb_info(session, title):
    override = MANUAL_ID_OVERRIDES.get(title)
    if not override:
        return None

    media_type = override["type"]
    media_id = override["id"]
    url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&language=en-US"

    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"TMDb API error for '{title}': Status {response.status}")
    except Exception as e:
        print(f"Request error for '{title}': {e}")
    return None


async def enrich_program(session, programme):
    title_elem = programme.find("title")
    if title_elem is None:
        return

    title = title_elem.text
    info = await fetch_tmdb_info(session, title)
    if not info:
        return

    desc = info.get("overview")
    poster = info.get("poster_path")
    if desc:
        desc_elem = ET.SubElement(programme, "desc", lang="en")
        desc_elem.text = desc
    if poster:
        icon_elem = ET.SubElement(programme, "icon", src=f"https://image.tmdb.org/t/p/w500{poster}")


async def main(epg_input, epg_output):
    tree = ET.parse(epg_input)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [enrich_program(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(epg_output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python3 enrich_epg.py <input.xml> <output.xml>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    asyncio.run(main(input_file, output_file))