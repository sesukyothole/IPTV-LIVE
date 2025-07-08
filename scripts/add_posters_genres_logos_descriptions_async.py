import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json
import time
import re

API_KEY = os.environ.get('TMDB_API_KEY')

EPG_INPUT = "epg.xml"
EPG_OUTPUT = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"

TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Load or initialize cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        tmdb_cache = json.load(f)
else:
    tmdb_cache = {}

def clean_title(title):
    title = re.sub(r"\(\d{4}\)", "", title)  # Remove years
    title = re.split("[-:]", title)[0]       # Remove subtitles
    return title.strip()

async def fetch_json(session, url, params):
    try:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as resp:
                return await resp.json()
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return {}

async def search_tmdb(session, title):
    if title in tmdb_cache:
        print(f"⚡ Cache hit: {title}")
        return tmdb_cache[title]

    query = clean_title(title)
    print(f"🔍 Searching TMDb for: {query}")

    result_data = {'poster': None, 'genres': [], 'description': None}

    # Try TV
    tv = await fetch_json(session, TMDB_SEARCH_TV, {"api_key": API_KEY, "query": query})
    if tv.get("results"):
        show = tv["results"][0]
        result_data['poster'] = TMDB_IMAGE + show.get("poster_path", "") if show.get("poster_path") else None
        result_data['genres'] = [genre['name'] for genre in show.get('genre_ids', [])]
        result_data['description'] = show.get("overview")
        tmdb_cache[title] = result_data
        return result_data

    # Try Movie
    movie = await fetch_json(session, TMDB_SEARCH_MOVIE, {"api_key": API_KEY, "query": query})
    if movie.get("results"):
        film = movie["results"][0]
        result_data['poster'] = TMDB_IMAGE + film.get("poster_path", "") if film.get("poster_path") else None
        result_data['genres'] = [genre['name'] for genre in film.get('genre_ids', [])]
        result_data['description'] = film.get("overview")
        tmdb_cache[title] = result_data
        return result_data

    print(f"❌ No match found for: {title}")
    tmdb_cache[title] = result_data
    return result_data

async def process_programme(session, programme):
    title_elem = programme.find("title")
    if title_elem is None:
        return

    channel_id = programme.get("channel")
    if channel_id not in TARGET_CHANNELS:
        return

    title = title_elem.text.strip()
    print(f"\n➡️ Processing: {title}")

    result = await search_tmdb(session, title)

    # Poster
    if result['poster']:
        ET.SubElement(programme, "icon", {"src": result['poster']})
        print(f"🖼️ Poster added: {result['poster']}")
    else:
        print(f"🚫 No poster found")

    # Genres
    if result['genres']:
        for genre in result['genres']:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🎯 Genres added: {', '.join(result['genres'])}")
    else:
        print("🚫 No genres found")

    # Description
    if result['description']:
        desc = programme.find("desc")
        if desc is None:
            desc = ET.SubElement(programme, "desc")
        desc.text = result['description']
        print("📄 Description added")
    else:
        print("🚫 No description found")

    await asyncio.sleep(0.25)  # Rate limiting

async def enrich_epg():
    tree = ET.parse(EPG_INPUT)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(EPG_OUTPUT, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Done! Updated EPG saved to {EPG_OUTPUT}")

    with open(CACHE_FILE, 'w') as f:
        json.dump(tmdb_cache, f)

if __name__ == "__main__":
    asyncio.run(enrich_epg())
