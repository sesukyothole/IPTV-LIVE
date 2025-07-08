import aiohttp
import asyncio
import async_timeout
import os
import xml.etree.ElementTree as ET
import json
import time

API_KEY = os.environ.get('TMDB_API_KEY')
INPUT_FILE = 'epg.xml'
OUTPUT_FILE = 'epg_updated.xml'
CACHE_FILE = 'poster_genre_cache.json'
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Load or initialize cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
else:
    cache = {}

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as response:
            return await response.json()

async def search_tmdb(session, title):
    if title in cache:
        print(f"⚡ Cache hit for: {title}")
        return cache[title]

    print(f"🔍 Searching TMDb for: {title}")
    result_data = {
        'poster': None,
        'overview': None,
        'genres': []
    }

    for url, content_type in [(TMDB_SEARCH_TV_URL, 'tv'), (TMDB_SEARCH_MOVIE_URL, 'movie')]:
        data = await fetch_json(session, url, {"api_key": API_KEY, "query": title})
        results = data.get('results', [])
        if results:
            result = results[0]
            result_data['poster'] = TMDB_IMAGE_URL + result.get('poster_path') if result.get('poster_path') else None
            result_data['overview'] = result.get('overview', '')
            genres = await get_genres(session, result.get('id'), content_type)
            result_data['genres'] = genres
            cache[title] = result_data
            return result_data

    print(f"❌ No match found for: {title}")
    cache[title] = result_data
    return result_data

async def get_genres(session, tmdb_id, content_type='tv'):
    if not tmdb_id:
        return []
    url = f"https://api.themoviedb.org/3/{content_type}/{tmdb_id}"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [genre['name'] for genre in data.get('genres', [])]

def extract_season_episode(programme):
    ep_node = programme.find('episode-num[@system="xmltv_ns"]')
    if ep_node is not None:
        try:
            parts = ep_node.text.split('.')
            season = int(parts[0]) + 1
            episode = int(parts[1]) + 1
            return f"S{season:02}E{episode:02}"
        except:
            return None
    return None

async def process_programme(session, programme, index, total):
    channel = programme.get('channel')
    title_el = programme.find('title')
    if channel not in TARGET_CHANNELS or title_el is None:
        return

    title = title_el.text.strip()
    print(f"\n➡️ [{index}/{total}] {title}")

    result_data = await search_tmdb(session, title)

    # Poster
    if result_data['poster']:
        ET.SubElement(programme, 'icon').set('src', result_data['poster'])
        print(f"🖼️ Poster added: {result_data['poster']}")
    else:
        print("🚫 No poster found")

    # Description
    if result_data['overview']:
        desc = ET.SubElement(programme, 'desc')
        desc.text = result_data['overview']
        print("📝 Description added")
    else:
        print("🚫 No description found")

    # Genres
    if result_data['genres']:
        for genre in result_data['genres']:
            ET.SubElement(programme, 'category').text = genre
        print(f"🎯 Genres added: {', '.join(result_data['genres'])}")
    else:
        print("🚫 No genres found")

    # Season/Episode
    se = extract_season_episode(programme)
    if se:
        ET.SubElement(programme, 'episode-num', {'system': 'onscreen'}).text = se
        print(f"📺 Episode info added: {se}")
    else:
        print("🚫 No episode info found")

    await asyncio.sleep(0.3)  # slight delay to avoid API throttle

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()
    programmes = root.findall('programme')

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, programme in enumerate(programmes, start=1):
            tasks.append(process_programme(session, programme, i, len(programmes)))
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding='utf-8', xml_declaration=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)
    print(f"\n✅ Updated EPG saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
