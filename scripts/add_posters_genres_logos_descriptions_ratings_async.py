import aiohttp
import asyncio
import async_timeout
import os
import xml.etree.ElementTree as ET
import json

API_KEY = os.environ.get('TMDB_API_KEY')
INPUT_FILE = 'epg.xml'
OUTPUT_FILE = 'epg_updated.xml'
CACHE_FILE = 'poster_genre_rating_cache.json'

TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
else:
    cache = {}

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as resp:
            return await resp.json()

async def get_rating(session, content_id, content_type='movie'):
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}/release_dates" if content_type == 'movie' else f"https://api.themoviedb.org/3/{content_type}/{content_id}/content_ratings"
    data = await fetch_json(session, url, {"api_key": API_KEY})

    if content_type == 'movie':
        for entry in data.get("results", []):
            if entry.get("iso_3166_1") == "US":
                for rel in entry.get("release_dates", []):
                    if "certification" in rel and rel["certification"]:
                        return rel["certification"]
    else:
        for entry in data.get("results", []):
            if entry.get("iso_3166_1") == "US" and entry.get("rating"):
                return entry.get("rating")

    return None

async def get_genres(session, tmdb_id, content_type='movie'):
    url = f"https://api.themoviedb.org/3/{content_type}/{tmdb_id}"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [genre['name'] for genre in data.get('genres', [])]

async def search_tmdb(session, title):
    if title in cache:
        print(f"⚡ Cache hit for: {title}")
        return cache[title]

    print(f"🔍 Searching for: {title}")
    result = {
        'poster': None,
        'overview': None,
        'genres': [],
        'rating': None
    }

    # Search TV
    tv_data = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": title})
    if tv_data.get("results"):
        tv = tv_data["results"][0]
        tmdb_id = tv["id"]
        result["poster"] = TMDB_IMAGE_URL + tv["poster_path"] if tv.get("poster_path") else None
        result["overview"] = tv.get("overview")
        result["genres"] = await get_genres(session, tmdb_id, "tv")
        result["rating"] = await get_rating(session, tmdb_id, "tv")
        cache[title] = result
        return result

    # Search Movie
    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": title})
    if movie_data.get("results"):
        movie = movie_data["results"][0]
        tmdb_id = movie["id"]
        result["poster"] = TMDB_IMAGE_URL + movie["poster_path"] if movie.get("poster_path") else None
        result["overview"] = movie.get("overview")
        result["genres"] = await get_genres(session, tmdb_id, "movie")
        result["rating"] = await get_rating(session, tmdb_id, "movie")
        cache[title] = result
        return result

    print(f"❌ No results for: {title}")
    cache[title] = result
    return result

async def process_programme(session, programme, index, total):
    channel = programme.get('channel')
    title_el = programme.find('title')

    if not title_el or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n➡️ [{index}/{total}] {title}")
    data = await search_tmdb(session, title)

    # Poster
    if data['poster']:
        ET.SubElement(programme, 'icon').set('src', data['poster'])
        print(f"🖼️ Poster added: {data['poster']}")
    else:
        print("🚫 No poster found")

    # Overview
    if data['overview']:
        ET.SubElement(programme, 'desc').text = data['overview']
        print("📝 Description added")
    else:
        print("🚫 No description")

    # Genres
    if data['genres']:
        for g in data['genres']:
            ET.SubElement(programme, 'category').text = g
        print(f"🎯 Genres added: {', '.join(data['genres'])}")
    else:
        print("🚫 No genres found")

    # Rating
    if data['rating']:
        ET.SubElement(programme, 'rating', {'system': 'MPAA'}).text = data['rating']
        print(f"🔞 Rating added: {data['rating']}")
    else:
        print("🚫 No rating found")

    await asyncio.sleep(0.25)  # respect TMDB limits

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()
    programmes = root.findall('programme')

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, prog in enumerate(programmes, start=1):
            tasks.append(process_programme(session, prog, i, len(programmes)))
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding='utf-8', xml_declaration=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)
    print(f"\n✅ EPG written to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
