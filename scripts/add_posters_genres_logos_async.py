import asyncio
import aiohttp
import async_timeout
import os
import xml.etree.ElementTree as ET
import json

API_KEY = os.environ['TMDB_API_KEY']
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

CHANNEL_LOGOS = {
    "403788": "https://example.com/logos/disney_east.png",
    "403674": "https://example.com/logos/nickelodeon.png",
    "403837": "https://example.com/logos/cartoon_network.png",
    "403794": "https://example.com/logos/boomerang.png",
    "403620": "https://example.com/logos/disney_junior.png",
    "403655": "https://example.com/logos/disney_channel.png",
    "8359":    "https://example.com/logos/pbs_kids.png",
    "403847": "https://example.com/logos/fx.png",
    "403461": "https://example.com/logos/abc_family.png",
    "403576": "https://example.com/logos/nicktoons.png"
}

TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Load or create cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    try:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except Exception:
        return {}

async def get_genres(session, tmdb_id, content_type):
    url = f"https://api.themoviedb.org/3/{content_type}/{tmdb_id}"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [genre['name'] for genre in data.get("genres", [])]

async def search_tmdb(session, query):
    if query in poster_cache:
        return poster_cache[query]

    result_data = {'portrait': None, 'genres': []}

    for endpoint, ctype in [(TMDB_SEARCH_TV, "tv"), (TMDB_SEARCH_MOVIE, "movie")]:
        data = await fetch_json(session, endpoint, {"api_key": API_KEY, "query": query})
        results = data.get("results", [])
        if results:
            item = results[0]
            if item.get("poster_path"):
                result_data['portrait'] = TMDB_IMAGE_URL + item["poster_path"]
            result_data['genres'] = await get_genres(session, item["id"], ctype)
            break

    poster_cache[query] = result_data
    return result_data

async def process_programme(session, programme, index, total):
    channel_id = programme.get("channel")
    title_el = programme.find("title")
    if channel_id in TARGET_CHANNELS and title_el is not None:
        title = title_el.text.strip()
        print(f"➡️ [{index}/{total}] Processing: {title}")
        result_data = await search_tmdb(session, title)

        if result_data["portrait"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", result_data["portrait"])
            print(f"✅ Poster added: {result_data['portrait']}")

        if result_data["genres"]:
            for g in result_data["genres"]:
                cat = ET.SubElement(programme, "category")
                cat.text = g
            print(f"🎯 Genres: {', '.join(result_data['genres'])}")

async def add_posters_async():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    # Add logos to channel tags
    for channel in root.findall("channel"):
        cid = channel.get("id")
        if cid in CHANNEL_LOGOS:
            icon = channel.find("icon")
            if icon is None:
                icon = ET.SubElement(channel, "icon")
            icon.set("src", CHANNEL_LOGOS[cid])
            print(f"📺 Logo added for channel {cid}")

    # Process programmes
    programmes = root.findall("programme")
    total = len(programmes)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, programme in enumerate(programmes, start=1):
            tasks.append(process_programme(session, programme, i, total))
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"✅ Saved updated EPG to {OUTPUT_FILE}")

    with open(CACHE_FILE, "w") as f:
        json.dump(poster_cache, f)

    print("✅ Cache updated")

if __name__ == "__main__":
    asyncio.run(add_posters_async())
