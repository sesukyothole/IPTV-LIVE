import asyncio
import aiohttp
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

TMDB_API_KEY = os.environ['TMDB_API_KEY']

TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"

# Load cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
else:
    cache = {}

async def fetch_json(session, url, params=None):
    try:
        with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return {}

async def get_movie_rating(session, movie_id):
    url = f"{TMDB_BASE}/movie/{movie_id}/release_dates"
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
    for result in data.get("results", []):
        if result.get("iso_3166_1") == "US":
            for entry in result.get("release_dates", []):
                cert = entry.get("certification")
                if cert:
                    return cert
    return "N/A"

async def get_tv_rating(session, tv_id):
    url = f"{TMDB_BASE}/tv/{tv_id}/content_ratings"
    data = await fetch_json(session, {"api_key": TMDB_API_KEY})
    for rating in data.get("results", []):
        if rating.get("iso_3166_1") == "US":
            return rating.get("rating", "N/A")
    return "N/A"

async def get_genres(session, tmdb_id, content_type):
    url = f"{TMDB_BASE}/{content_type}/{tmdb_id}"
    data = await fetch_json(session, {"api_key": TMDB_API_KEY})
    return [genre["name"] for genre in data.get("genres", [])]

async def search_tmdb(session, title):
    if title in cache:
        print(f"⚡ Cache hit: {title}")
        return cache[title]

    print(f"🔍 Searching for: {title}")

    # Try TV show first
    tv_resp = await fetch_json(session, f"{TMDB_BASE}/search/tv", {"api_key": TMDB_API_KEY, "query": title})
    if tv_resp.get("results"):
        tv = tv_resp["results"][0]
        tv_id = tv["id"]
        result = {
            "type": "tv",
            "id": tv_id,
            "poster": IMAGE_BASE + tv["poster_path"] if tv.get("poster_path") else None,
            "genres": await get_genres(session, tv_id, "tv"),
            "rating": await get_tv_rating(session, tv_id)
        }
        cache[title] = result
        print(f"✅ TV Show found: {title}")
        return result

    # Try Movie
    movie_resp = await fetch_json(session, f"{TMDB_BASE}/search/movie", {"api_key": TMDB_API_KEY, "query": title})
    if movie_resp.get("results"):
        movie = movie_resp["results"][0]
        movie_id = movie["id"]
        result = {
            "type": "movie",
            "id": movie_id,
            "poster": IMAGE_BASE + movie["poster_path"] if movie.get("poster_path") else None,
            "genres": await get_genres(session, movie_id, "movie"),
            "rating": await get_movie_rating(session, movie_id)
        }
        cache[title] = result
        print(f"✅ Movie found: {title}")
        return result

    print(f"❌ Not found: {title}")
    result = {"type": "none", "poster": None, "genres": [], "rating": "N/A"}
    cache[title] = result
    return result

async def process_programme(session, programme):
    channel_id = programme.get("channel")
    title_el = programme.find("title")
    if channel_id not in TARGET_CHANNELS or title_el is None:
        return

    title = title_el.text
    result = await search_tmdb(session, title)

    if result["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", result["poster"])
        print(f"🖼️ Poster added for: {title}")
    else:
        print(f"⚠️ No poster for: {title}")

    if result["genres"]:
        for genre in result["genres"]:
            category = ET.SubElement(programme, "category")
            category.text = genre
        print(f"🏷️ Genres: {', '.join(result['genres'])}")
    else:
        print(f"⚠️ No genres for: {title}")

    if result["rating"] != "N/A":
        rating_el = ET.SubElement(programme, "rating")
        value_el = ET.SubElement(rating_el, "value")
        value_el.text = result["rating"]
        print(f"🔞 Rating for {title}: {result['rating']}")
    else:
        print(f"❌ No rating found for: {title}")

    await asyncio.sleep(0.3)

async def enrich_epg():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

    print(f"\n✅ Finished. Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(enrich_epg())
