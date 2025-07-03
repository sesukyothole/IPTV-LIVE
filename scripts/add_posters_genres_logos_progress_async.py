import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import json
from datetime import datetime

# TMDb API Key
API_KEY = os.environ['TMDB_API_KEY']

# Channels to process (update with your channel IDs)
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

# Channel logos (always visible)
CHANNEL_LOGOS = {
    "403788": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s10171_dark_360w_270h.png",
    "403674": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s74796_dark_360w_270h.png",
    "403837": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s18279_dark_360w_270h.png",
    "403794": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/freeform-us.png",
    "403620": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s11006_dark_360w_270h.png",
    "403655": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s19211_dark_360w_270h.png",
    "8359": "https://github.com/tv-logo/tv-logos/blob/main/countries/united-states/nick-music-us.png?raw=true",
    "403847": "https://github.com/tv-logo/tv-logos/blob/main/countries/united-states/nick-toons-us.png?raw=true",
    "403461": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cartoon-network-us.png",
    "403576": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/boomerang-us.png"
}

# TMDb URLs
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Files
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

# Load or create cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def search_tmdb(session, query):
    if query in poster_cache:
        print(f"⚡ Cache hit for: {query}")
        return poster_cache[query]

    print(f"🔍 Searching TMDb for: {query}")
    result_data = {'landscape': None, 'portrait': None, 'genres': []}

    # Try TV first
    data = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": query})
    results = data.get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            result_data['landscape'] = TMDB_IMAGE_URL + result['backdrop_path']
        if result.get('poster_path'):
            result_data['portrait'] = TMDB_IMAGE_URL + result['poster_path']
        result_data['genres'] = await get_genres(session, result['id'], content_type='tv')
        poster_cache[query] = result_data
        return result_data

    # Try Movie
    data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": query})
    results = data.get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            result_data['landscape'] = TMDB_IMAGE_URL + result['backdrop_path']
        if result.get('poster_path'):
            result_data['portrait'] = TMDB_IMAGE_URL + result['poster_path']
        result_data['genres'] = await get_genres(session, result['id'], content_type='movie')
        poster_cache[query] = result_data
        return result_data

    poster_cache[query] = result_data
    return result_data

async def get_genres(session, content_id, content_type='tv'):
    if content_id is None:
        return []
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}"
    async with session.get(url, params={"api_key": API_KEY}) as response:
        if response.status != 200:
            return []
        data = await response.json()
        genres = data.get('genres', [])
        return [genre['name'] for genre in genres]

async def process_programme(session, programme, idx, total):
    channel_id = programme.get('channel')
    title_element = programme.find('title')

    if channel_id in TARGET_CHANNELS and title_element is not None:
        title = title_element.text
        print(f"➡️ [{idx}/{total}] Processing: {title}")

        # Calculate and add progress bar
        start = programme.get('start')
        stop = programme.get('stop')

        if start and stop:
            start_time = datetime.strptime(start[:14], '%Y%m%d%H%M%S')
            stop_time = datetime.strptime(stop[:14], '%Y%m%d%H%M%S')
            now = datetime.utcnow()

            if start_time <= now <= stop_time:
                progress = int(((now - start_time).total_seconds() / (stop_time - start_time).total_seconds()) * 100)
                progress_element = ET.SubElement(programme, 'progress')
                progress_element.text = str(progress)
                print(f"📊 Progress: {progress}%")
            else:
                print(f"⏱️ Program is not currently airing.")

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

def add_channel_logos(epg_tree):
    root = epg_tree.getroot()

    for channel in root.findall('channel'):
        channel_id = channel.get('id')

        if channel_id in CHANNEL_LOGOS:
            icon_element = channel.find('icon')
            if icon_element is None:
                icon_element = ET.SubElement(channel, 'icon')
            icon_element.set('src', CHANNEL_LOGOS[channel_id])
            print(f"✅ Channel logo added for channel: {channel_id}")

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    programmes = root.findall('programme')
    total_programmes = len(programmes)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, programme in enumerate(programmes, 1):
            channel_id = programme.get('channel')
            if channel_id in TARGET_CHANNELS:
                tasks.append(process_programme(session, programme, idx, total_programmes))

                if len(tasks) % 35 == 0:  # TMDb rate limit protection
                    await asyncio.gather(*tasks)
                    tasks = []
                    await asyncio.sleep(10)

        if tasks:
            await asyncio.gather(*tasks)

    add_channel_logos(tree)
    tree.write(OUTPUT_FILE, encoding='utf-8', xml_declaration=True)

    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)

    print(f"\n✅ EPG fully updated with Posters, Genres, Channel Logos, and Progress Bars saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
