import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

API_KEY = os.environ["TMDB_API_KEY"]
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"
SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        tmdb_cache = json.load(f)
else:
    tmdb_cache = {}

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as response:
            return await response.json()

async def get_tmdb_data(session, title):
    if title in tmdb_cache:
        print(f"⚡ Cached: {title}")
        return tmdb_cache[title]

    print(f"\n🔍 Searching TMDb for: {title}")
    data = {
        "poster": None,
        "description": None,
        "genres": [],
        "season_episode": None
    }

    # Try TV show first
    search_tv = await fetch_json(session, SEARCH_TV_URL, {"api_key": API_KEY, "query": title})
    if search_tv.get("results"):
        show = search_tv["results"][0]
        show_id = show["id"]
        data["poster"] = TMDB_IMAGE + show["poster_path"] if show.get("poster_path") else None
        data["description"] = show.get("overview")

        # Get genres
        details = await fetch_json(session, f"https://api.themoviedb.org/3/tv/{show_id}", {"api_key": API_KEY})
        data["genres"] = [g["name"] for g in details.get("genres", [])]

        # Try to find season/episode
        if details.get("last_episode_to_air"):
            last = details["last_episode_to_air"]
            data["season_episode"] = f"S{str(last['season_number']).zfill(2)}E{str(last['episode_number']).zfill(2)}"

        tmdb_cache[title] = data
        return data

    # Try movie
    search_movie = await fetch_json(session, SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": title})
    if search_movie.get("results"):
        movie = search_movie["results"][0]
        data["poster"] = TMDB_IMAGE + movie["poster_path"] if movie.get("poster_path") else None
        data["description"] = movie.get("overview")

        # Get genres
        details = await fetch_json(session, f"https://api.themoviedb.org/3/movie/{movie['id']}", {"api_key": API_KEY})
        data["genres"] = [g["name"] for g in details.get("genres", [])]

    tmdb_cache[title] = data
    return data

async def process_programme(session, programme):
    channel_id = programme.get("channel")
    title_el = programme.find("title")
    if channel_id not in TARGET_CHANNELS or title_el is None:
        return

    title = title_el.text.strip()
    print(f"\n🎬 Title: {title}")
    data = await get_tmdb_data(session, title)

    if data["poster"]:
        ET.SubElement(programme, "icon", {"src": data["poster"]})
        print("🖼️ Poster added")
    else:
        print("🚫 No poster found")

    desc_text = data["description"] or "No description available"
    if data["season_episode"]:
        desc_text += f"\n📺 Episode: {data['season_episode']}"

    desc_el = programme.find("desc")
    if desc_el is None:
        desc_el = ET.SubElement(programme, "desc", {"lang": "en"})
    desc_el.text = desc_text
    print("📃 Description added")

    if data["genres"]:
        for genre in data["genres"]:
            ET.SubElement(programme, "category").text = genre
        print(f"🎯 Genres added: {', '.join(data['genres'])}")
    else:
        print("🚫 No genres found")

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()
    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG updated and saved to {OUTPUT_FILE}")

    with open(CACHE_FILE, 'w') as f:
        json.dump(tmdb_cache, f)
    print("💾 Cache saved")

if __name__ == "__main__":
    asyncio.run(main())
