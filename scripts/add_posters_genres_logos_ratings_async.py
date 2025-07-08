import asyncio
import aiohttp
import async_timeout
import xml.etree.ElementTree as ET
import os
import time
import json

TMDB_API_KEY = os.environ['TMDB_API_KEY']
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_MOVIE_DETAILS_URL = "https://api.themoviedb.org/3/movie/{}"
TMDB_TV_RATINGS_URL = "https://api.themoviedb.org/3/tv/{}/content_ratings"

INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

# Load or create cache
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
    url = TMDB_MOVIE_DETAILS_URL.format(movie_id)
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
    return data.get("release_dates", [{}])[0].get("certification", "N/A")

async def get_tv_rating(session, tv_id):
    url = TMDB_TV_RATINGS_URL.format(tv_id)
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "US":
            return entry.get("rating", "N/A")
    return "N/A"

async def get_genres(session, tmdb_id, content_type):
    url = f"https://api.themoviedb.org/3/{content_type}/{tmdb_id}"
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
    return [genre["name"] for genre in data.get("genres", [])]

async def search_tmdb(session, title):
    if title in cache:
        print(f"⚡ Cache hit: {title}")
        return cache[title]

    print(f"🔍 Searching for: {title}")

    # Try TV
    tv_response = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": TMDB_API_KEY, "query": title})
    if tv_response.get("results"):
        result = tv_response["results"][0]
        data = {
            "type": "tv",
            "id": result["id"],
            "poster": TMDB_IMAGE_URL + result["poster_path"] if result.get("poster_path") else None,
            "genres": await get_genres(session, result["id"], "tv"),
            "rating": await get_tv_rating(session, result["id"]),
        }
        cache[title] = data
        print(f"✅ Found TV: {title}")
        return data

    # Try Movie
    movie_response = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": TMDB_API_KEY, "query": title})
    if movie_response.get("results"):
        result = movie_response["results"][0]
        data = {
            "type": "movie",
            "id": result["id"],
            "poster": TMDB_IMAGE_URL + result["poster_path"] if result.get("poster_path") else None,
            "genres": await get_genres(session, result["id"], "movie"),
            "rating": await get_movie_rating(session, result["id"]),
        }
        cache[title] = data
        print(f"✅ Found Movie: {title}")
        return data

    print(f"❌ Not found: {title}")
    cache[title] = {"type": "none", "poster": None, "genres": [], "rating": "N/A"}
    return cache[title]

async def process_programme(session, programme):
    channel_id = programme.attrib.get("channel")
    title_element = programme.find("title")
    if channel_id not in TARGET_CHANNELS or title_element is None:
        return

    title = title_element.text
    result = await search_tmdb(session, title)

    if result["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", result["poster"])
        print(f"🖼️ Poster added: {result['poster']}")

    if result["genres"]:
        for genre in result["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🏷️ Genres: {', '.join(result['genres'])}")
    else:
        print(f"⚠️ No genres found for: {title}")

    rating = result.get("rating", "N/A")
    if rating != "N/A":
        rating_el = ET.SubElement(programme, "rating")
        rating_val = ET.SubElement(rating_el, "value")
        rating_val.text = rating
        print(f"🔞 Rating: {rating}")
    else:
        print(f"⚠️ No rating for: {title}")

    await asyncio.sleep(0.3)  # TMDb rate limit handling

async def enrich_epg():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for prog in root.findall("programme"):
            tasks.append(process_programme(session, prog))
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)
    print(f"\n✅ EPG enrichment complete. Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(enrich_epg())
