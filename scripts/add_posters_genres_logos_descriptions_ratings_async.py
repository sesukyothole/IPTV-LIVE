import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json
import re

API_KEY = os.environ.get('TMDB_API_KEY')

INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"

TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        tmdb_cache = json.load(f)
else:
    tmdb_cache = {}

def clean_title(title):
    title = re.sub(r'\(\d{4}\)', '', title)
    title = re.split(r'[-:]', title)[0]
    return title.strip()

async def fetch_json(session, url, params=None):
    try:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return {}

async def get_tv_rating(session, tv_id):
    url = f"{TMDB_BASE_URL}/tv/{tv_id}/content_ratings"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    for rating in data.get("results", []):
        if rating["iso_3166_1"] == "US":
            return rating["rating"]
    return None

async def get_movie_rating(session, movie_id):
    url = f"{TMDB_BASE_URL}/movie/{movie_id}/release_dates"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    for release in data.get("results", []):
        if release["iso_3166_1"] == "US":
            for entry in release.get("release_dates", []):
                if "certification" in entry and entry["certification"]:
                    return entry["certification"]
    return None

async def search_tmdb(session, title):
    if title in tmdb_cache:
        print(f"⚡ Cache hit: {title}")
        return tmdb_cache[title]

    print(f"🔍 Searching TMDb for: {title}")
    result = {
        "poster": None,
        "genres": [],
        "description": None,
        "rating": None
    }

    # TV Search
    tv_data = await fetch_json(session, f"{TMDB_BASE_URL}/search/tv", {"api_key": API_KEY, "query": title})
    if tv_data.get("results"):
        tv = tv_data["results"][0]
        result["poster"] = IMAGE_BASE_URL + tv["poster_path"] if tv.get("poster_path") else None
        result["description"] = tv.get("overview")
        result["genres"] = [str(tv.get("genre_ids", []))]
        result["rating"] = await get_tv_rating(session, tv["id"])
        tmdb_cache[title] = result
        return result

    # Movie Search
    movie_data = await fetch_json(session, f"{TMDB_BASE_URL}/search/movie", {"api_key": API_KEY, "query": title})
    if movie_data.get("results"):
        movie = movie_data["results"][0]
        result["poster"] = IMAGE_BASE_URL + movie["poster_path"] if movie.get("poster_path") else None
        result["description"] = movie.get("overview")
        result["genres"] = [str(movie.get("genre_ids", []))]
        result["rating"] = await get_movie_rating(session, movie["id"])
        tmdb_cache[title] = result
        return result

    print(f"❌ No TMDb data found for: {title}")
    tmdb_cache[title] = result
    return result

async def process_programme(session, programme):
    title_elem = programme.find("title")
    if title_elem is None:
        return

    channel_id = programme.get("channel")
    if channel_id not in TARGET_CHANNELS:
        return

    title = clean_title(title_elem.text or "")
    print(f"\n➡️ Processing: {title}")

    data = await search_tmdb(session, title)

    if data["poster"]:
        ET.SubElement(programme, "icon", {"src": data["poster"]})
        print(f"🖼️ Poster added")
    else:
        print("🚫 No poster found")

    if data["genres"]:
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🎯 Genres added")
    else:
        print("🚫 No genres found")

    if data["description"]:
        desc = programme.find("desc")
        if desc is None:
            desc = ET.SubElement(programme, "desc")
        desc.text = data["description"]
        print("📄 Description added")
    else:
        print("🚫 No description found")

    if data["rating"]:
        rating_elem = ET.SubElement(programme, "rating")
        value = ET.SubElement(rating_elem, "value")
        value.text = data["rating"]
        print(f"🔞 Rating added: {data['rating']}")
    else:
        print("🚫 No rating found")

    await asyncio.sleep(0.25)  # Rate limiting

async def enrich_epg():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, prog) for prog in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG saved to {OUTPUT_FILE}")

    with open(CACHE_FILE, "w") as f:
        json.dump(tmdb_cache, f)

if __name__ == "__main__":
    asyncio.run(enrich_epg())
