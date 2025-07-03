import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import json

API_KEY = os.environ['TMDB_API_KEY']

TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

# Load or create poster cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

semaphore = asyncio.Semaphore(20)  # Limit to 20 concurrent requests

async def fetch_json(session, url, params):
    async with semaphore:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"❌ TMDb API error: {response.status} for {url} with {params}")
                    return None
        except asyncio.TimeoutError:
            print(f"⏰ Request timed out for: {url} with {params}")
            return None

async def get_genres(session, content_id, content_type):
    if content_id is None:
        return []
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}"
    params = {"api_key": API_KEY}
    data = await fetch_json(session, url, params)
    if data and 'genres' in data:
        return [genre['name'] for genre in data['genres']]
    return []

async def search_tmdb(session, query):
    if query in poster_cache:
        return poster_cache[query]

    # Search TV Shows
    data = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": query})
    if data and data.get('results'):
        result = data['results'][0]
        landscape = TMDB_IMAGE_URL + result['backdrop_path'] if result.get('backdrop_path') else None
        portrait = TMDB_IMAGE_URL + result['poster_path'] if result.get('poster_path') else None
        genres = await get_genres(session, result.get('id'), 'tv')
        poster_cache[query] = {'landscape': landscape, 'portrait': portrait, 'genres': genres}
        return poster_cache[query]

    # Search Movies
    data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": query})
    if data and data.get('results'):
        result = data['results'][0]
        landscape = TMDB_IMAGE_URL + result['backdrop_path'] if result.get('backdrop_path') else None
        portrait = TMDB_IMAGE_URL + result['poster_path'] if result.get('poster_path') else None
        genres = await get_genres(session, result.get('id'), 'movie')
        poster_cache[query] = {'landscape': landscape, 'portrait': portrait, 'genres': genres}
        return poster_cache[query]

    poster_cache[query] = {'landscape': None, 'portrait': None, 'genres': []}
    return poster_cache[query]

async def process_programme(session, programme, idx, total):
    channel_id = programme.get('channel')
    title_element = programme.find('title')

    if channel_id in TARGET_CHANNELS and title_element is not None:
        title = title_element.text
        print(f"➡️ [{idx}/{total}] Processing: {title}")

        result_data = await search_tmdb(session, title)

        added_something = False

        if result_data['landscape']:
            icon_landscape = ET.SubElement(programme, 'icon')
            icon_landscape.set('src', result_data['landscape'])
            print(f"✅ Landscape poster added: {result_data['landscape']}")
            added_something = True

        if result_data['portrait']:
            icon_portrait = ET.SubElement(programme, 'icon')
            icon_portrait.set('src', result_data['portrait'])
            print(f"✅ Portrait poster added: {result_data['portrait']}")
            added_something = True

        if result_data['genres']:
            for genre in result_data['genres']:
                category = ET.SubElement(programme, 'category')
                category.text = genre
            print(f"🎯 Genres added: {', '.join(result_data['genres'])}")
            added_something = True

        if not added_something:
            print(f"❌ No poster or genre found for: {title}")

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    programmes = root.findall('programme')
    total_programmes = len(programmes)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, programme in enumerate(programmes, 1):
            task = process_programme(session, programme, idx, total_programmes)
            tasks.append(task)

        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding='utf-8', xml_declaration=True)
    print(f"\n✅ EPG updated and saved to {OUTPUT_FILE}")

    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)
    print("✅ Poster and genre cache saved successfully!")

if __name__ == "__main__":
    asyncio.run(main())
