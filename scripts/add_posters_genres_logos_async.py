import asyncio
import aiohttp
import async_timeout
import xml.etree.ElementTree as ET
import os
import time
import json
import sys

API_KEY = os.environ['TMDB_API_KEY']
INPUT_FILE = sys.argv[1]
OUTPUT_FILE = sys.argv[2]
CACHE_FILE = "poster_genre_cache.json"

TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

# Channel Logos Map
CHANNEL_LOGOS = {
    "403788": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s10171_dark_360w_270h.png",
    "403674": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s74796_dark_360w_270h.png",
    "403837": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s18279_dark_360w_270h.png",
    "403794": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/freeform-us.png",
    "403620": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s11006_dark_360w_270h.png",
    "403655": "http://schedulesdirect-api20141201-logos.s3.dualstack.us-east-1.amazonaws.com/stationLogos/s19211_dark_360w_270h.png",
    "8359":   "https://github.com/tv-logo/tv-logos/blob/main/countries/united-states/nick-music-us.png?raw=true",
    "403847": "https://github.com/tv-logo/tv-logos/blob/main/countries/united-states/nick-toons-us.png?raw=true",
    "403461": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cartoon-network-us.png",
    "403576": "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/boomerang-us.png"
}

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_DETAILS_URL = "https://api.themoviedb.org/3/{type}/{id}"

# Load poster+genre cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    try:
        with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except Exception:
        return {}

async def get_genres(session, content_id, content_type='tv'):
    url = TMDB_DETAILS_URL.format(type=content_type, id=content_id)
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [g['name'] for g in data.get('genres', [])] if data else []

async def search_tmdb(session, query):
    if query in poster_cache:
        return poster_cache[query]

    result_data = {'portrait': None, 'genres': []}

    tv_data = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": query})
    if tv_data.get('results'):
        tv = tv_data['results'][0]
        result_data['portrait'] = TMDB_IMAGE_URL + tv.get('poster_path', '')
        result_data['genres'] = await get_genres(session, tv['id'], 'tv')
        poster_cache[query] = result_data
        return result_data

    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": query})
    if movie_data.get('results'):
        movie = movie_data['results'][0]
        result_data['portrait'] = TMDB_IMAGE_URL + movie.get('poster_path', '')
        result_data['genres'] = await get_genres(session, movie['id'], 'movie')
        poster_cache[query] = result_data
        return result_data

    poster_cache[query] = result_data
    return result_data

async def process_programme(session, programme, index, total):
    channel_id = programme.get('channel')
    title_element = programme.find('title')

    if channel_id not in TARGET_CHANNELS or title_element is None:
        return

    title = title_element.text
    print(f"🔄 [{index}/{total}] Processing: {title}")

    result = await search_tmdb(session, title)

    if result['portrait']:
        ET.SubElement(programme, 'icon').set('src', result['portrait'])

    for genre in result['genres']:
        category = ET.SubElement(programme, 'category')
        category.text = genre

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    # Add logos to channel section
    for channel in root.findall('channel'):
        chan_id = channel.get('id')
        if chan_id in CHANNEL_LOGOS:
            icon = channel.find('icon')
            if icon is None:
                ET.SubElement(channel, 'icon').set('src', CHANNEL_LOGOS[chan_id])
            else:
                icon.set('src', CHANNEL_LOGOS[chan_id])

    programmes = root.findall('programme')
    total = len(programmes)

    async with aiohttp.ClientSession() as session:
        tasks = [
            process_programme(session, prog, idx + 1, total)
            for idx, prog in enumerate(programmes)
        ]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)

    print(f"✅ EPG updated and saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
