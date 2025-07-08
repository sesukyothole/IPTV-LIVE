import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

TMDB_API_KEY = os.environ['TMDB_API_KEY']
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_DETAILS_URL = "https://api.themoviedb.org/3/{type}/{id}"
TMDB_CERTIFICATION_URL = "https://api.themoviedb.org/3/movie/{id}/release_dates"

# Load cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
else:
    cache = {}

async def fetch_json(session, url, params=None):
    try:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except Exception as e:
        print(f"⚠️ Error fetching JSON: {e}")
        return {}

async def search_tmdb(session, title):
    if title in cache:
        print(f"⚡ Cache hit: {title}")
        return cache[title]

    print(f"🔍 Searching TMDB for: {title}")
    result = {
        "poster": None,
        "genres": [],
        "rating": None
    }

    # Try TV
    tv_data = await fetch_json(session, TMDB_SEARCH_TV_URL, params={"api_key": TMDB_API_KEY, "query": title})
    if tv_data.get("results"):
        item = tv_data["results"][0]
        result["poster"] = TMDB_IMAGE_URL + item.get("poster_path", "") if item.get("poster_path") else None
        result["genres"] = await get_genres(session, item['id'], 'tv')
        result["rating"] = await get_age_rating_tv(session, item['id'])
        print(f"🎬 {title}: Poster {'added' if result['poster'] else 'not found'}, Rating: {result['rating'] or 'N/A'}")
        cache[title] = result
        return result

    # Try Movie
    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, params={"api_key": TMDB_API_KEY, "query": title})
    if movie_data.get("results"):
        item = movie_data["results"][0]
        result["poster"] = TMDB_IMAGE_URL + item.get("poster_path", "") if item.get("poster_path") else None
        result["genres"] = await get_genres(session, item['id'], 'movie')
        result["rating"] = await get_age_rating_movie(session, item['id'])
        print(f"🎬 {title}: Poster {'added' if result['poster'] else 'not found'}, Rating: {result['rating'] or 'N/A'}")
        cache[title] = result
        return result

    print(f"❌ {title}: No poster found.")
    cache[title] = result
    return result

async def get_genres(session, content_id, content_type):
    url = TMDB_DETAILS_URL.format(type=content_type, id=content_id)
    data = await fetch_json(session, url, params={"api_key": TMDB_API_KEY})
    return [genre['name'] for genre in data.get('genres', [])]

async def get_age_rating_movie(session, movie_id):
    url = TMDB_CERTIFICATION_URL.format(id=movie_id)
    data = await fetch_json(session, url, params={"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            for cert in entry["release_dates"]:
                rating = cert.get("certification")
                if rating:
                    return rating
    return None

async def get_age_rating_tv(session, tv_id):
    url = TMDB_DETAILS_URL.format(type="tv", id=tv_id)
    data = await fetch_json(session, url, params={"api_key": TMDB_API_KEY})
    return data.get("content_rating", None)

async def process_programme(session, programme):
    channel_id = programme.get('channel')
    if channel_id not in TARGET_CHANNELS:
        return

    title_elem = programme.find('title')
    if title_elem is None:
        return
    title = title_elem.text.strip()

    result = await search_tmdb(session, title)

    if result['poster']:
        icon_elem = ET.SubElement(programme, 'icon')
        icon_elem.set('src', result['poster'])

    for genre in result['genres']:
        cat = ET.SubElement(programme, 'category')
        cat.text = genre

    if result['rating']:
        rating_elem = ET.SubElement(programme, 'rating')
        value = ET.SubElement(rating_elem, 'value')
        value.text = result['rating']

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()
    programmes = root.findall('programme')

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding='utf-8', xml_declaration=True)
    print(f"\n✅ EPG updated and saved to {OUTPUT_FILE}")

    # Save cache
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)
    print("💾 Cache saved successfully.")

if __name__ == "__main__":
    asyncio.run(main())
