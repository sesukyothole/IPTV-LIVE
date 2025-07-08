import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

API_KEY = os.environ['TMDB_API_KEY']
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

TARGET_CHANNELS = {
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

TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    try:
        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()
    except:
        return {}

async def get_genres_and_rating(session, tmdb_id, type_):
    genres, rating = [], None

    if type_ == 'tv':
        details_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
        rating_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/content_ratings"
    else:
        details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        rating_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/release_dates"

    details = await fetch_json(session, details_url, {"api_key": API_KEY})
    if 'genres' in details:
        genres = [g['name'] for g in details['genres']]

    ratings = await fetch_json(session, rating_url, {"api_key": API_KEY})
    if type_ == 'tv':
        for item in ratings.get('results', []):
            if item['iso_3166_1'] == 'US':
                rating = item.get('rating')
                break
    else:
        for item in ratings.get('results', []):
            if item['iso_3166_1'] == 'US':
                for entry in item.get('release_dates', []):
                    if entry.get('certification'):
                        rating = entry['certification']
                        break

    return genres, rating

async def search_tmdb(session, title):
    if title in poster_cache:
        return poster_cache[title]

    print(f"🔍 Searching TMDb for: {title}")
    result_data = {'poster': None, 'genres': [], 'rating': None}

    response = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": title})
    results = response.get('results', [])
    if results:
        tmdb_id = results[0]['id']
        result_data['poster'] = TMDB_IMAGE_URL + results[0]['poster_path'] if results[0].get('poster_path') else None
        result_data['genres'], result_data['rating'] = await get_genres_and_rating(session, tmdb_id, 'tv')
        poster_cache[title] = result_data
        return result_data

    response = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": title})
    results = response.get('results', [])
    if results:
        tmdb_id = results[0]['id']
        result_data['poster'] = TMDB_IMAGE_URL + results[0]['poster_path'] if results[0].get('poster_path') else None
        result_data['genres'], result_data['rating'] = await get_genres_and_rating(session, tmdb_id, 'movie')
        poster_cache[title] = result_data
        return result_data

    poster_cache[title] = result_data
    return result_data

async def process_programme(session, programme):
    channel_id = programme.get('channel')
    if channel_id not in TARGET_CHANNELS:
        return

    title_element = programme.find('title')
    if title_element is None:
        return

    title = title_element.text.strip()
    print(f"🎬 Processing: {title}")
    result = await search_tmdb(session, title)

    # Add poster
    if result['poster']:
        icon = ET.SubElement(programme, 'icon')
        icon.set('src', result['poster'])
        print(f"✅ Poster added")

    # Add genres
    for genre in result['genres']:
        cat = ET.SubElement(programme, 'category')
        cat.text = genre
    if result['genres']:
        print(f"🏷️ Genres: {', '.join(result['genres'])}")

    # Add rating
    if result['rating']:
        rating_el = ET.SubElement(programme, 'rating')
        val = ET.SubElement(rating_el, 'value')
        val.text = result['rating']
        print(f"🔞 Rating: {result['rating']}")

    # Add progress bar
    now = int(ET.tostring(programme.get('start'), encoding='unicode'))
    ET.SubElement(programme, 'progress', {'enabled': 'true'})

async def add_all(session, root):
    tasks = [process_programme(session, prog) for prog in root.findall('programme')]
    await asyncio.gather(*tasks)

def inject_channel_logos(root):
    for channel in root.findall('channel'):
        cid = channel.get('id')
        if cid in TARGET_CHANNELS:
            icon = channel.find('icon')
            if icon is None:
                icon = ET.SubElement(channel, 'icon')
            icon.set('src', TARGET_CHANNELS[cid])

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    inject_channel_logos(root)

    async with aiohttp.ClientSession() as session:
        await add_all(session, root)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)

    print("✅ Done updating EPG with posters, genres, ratings, and logos.")

if __name__ == "__main__":
    asyncio.run(main())
