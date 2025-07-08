import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

# TMDb API Key
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

# Target channels (customize your list here)
TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Cache file
CACHE_FILE = "poster_genre_description_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        CACHE = json.load(f)
else:
    CACHE = {}

async def fetch_json(session, url, params):
    try:
        with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"❌ HTTP {response.status} for URL: {response.url}")
                    return {}
                return await response.json()
    except Exception as e:
        print(f"❌ Error fetching: {e}")
        return {}

async def search_tmdb(session, title):
    if title in CACHE:
        return CACHE[title]

    print(f"🔍 Searching TMDb for: {title}")
    result = {"poster": None, "genres": [], "description": None}

    # TV Show
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", {"api_key": TMDB_API_KEY, "query": title})
    if tv.get("results"):
        show = tv["results"][0]
        result["poster"] = TMDB_IMAGE + show["poster_path"] if show.get("poster_path") else None
        result["description"] = show.get("overview")

        # Fetch genres
        details = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}", {"api_key": TMDB_API_KEY})
        result["genres"] = [g["name"] for g in details.get("genres", [])]

        CACHE[title] = result
        return result

    # Movie fallback
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", {"api_key": TMDB_API_KEY, "query": title})
    if movie.get("results"):
        m = movie["results"][0]
        result["poster"] = TMDB_IMAGE + m["poster_path"] if m.get("poster_path") else None
        result["description"] = m.get("overview")

        # Fetch genres
        details = await fetch_json(session, f"{TMDB_BASE}/movie/{m['id']}", {"api_key": TMDB_API_KEY})
        result["genres"] = [g["name"] for g in details.get("genres", [])]

        CACHE[title] = result
        return result

    print(f"⚠️ No match found for {title}")
    CACHE[title] = result
    return result

async def process_programme(session, programme):
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        return

    title = title_el.text.strip()
    print(f"➡️ Processing: {title}")
    data = await search_tmdb(session, title)

    # Poster
    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print(f"✅ Poster added")
    else:
        print(f"⚠️ No poster")

    # Genres
    if data["genres"]:
        for genre in data["genres"]:
            category = ET.SubElement(programme, "category")
            category.text = genre
        print(f"🎯 Genres: {', '.join(data['genres'])}")
    else:
        print(f"⚠️ No genres")

    # Description
    if data["description"]:
        desc_el = programme.find("desc")
        if desc_el is None:
            desc_el = ET.SubElement(programme, "desc")
        desc_el.text = data["description"]
        print(f"📝 Description added")
    else:
        print(f"⚠️ No description")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

    with open(CACHE_FILE, "w") as f:
        json.dump(CACHE, f)
    print("💾 Cache saved")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_genres_descriptions_async.py epg.xml epg_updated.xml")
        exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
