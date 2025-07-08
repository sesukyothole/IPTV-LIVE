import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

API_KEY = os.environ["TMDB_API_KEY"]

# TMDb Endpoints
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Input and output
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

# Channels to process
TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Channel logos
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

# Load cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as response:
            return await response.json()

async def get_genres(session, content_id, content_type):
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [genre["name"] for genre in data.get("genres", [])]

async def search_tmdb(session, query):
    if query in poster_cache:
        print(f"⚡ Cache hit: {query}")
        return poster_cache[query]

    result_data = {"portrait": None, "genres": []}

    # Search TV
    data = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": API_KEY, "query": query})
    if data["results"]:
        result = data["results"][0]
        if result.get("poster_path"):
            result_data["portrait"] = TMDB_IMAGE_BASE + result["poster_path"]
        result_data["genres"] = await get_genres(session, result["id"], "tv")
        poster_cache[query] = result_data
        return result_data

    # Search Movies
    data = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": API_KEY, "query": query})
    if data["results"]:
        result = data["results"][0]
        if result.get("poster_path"):
            result_data["portrait"] = TMDB_IMAGE_BASE + result["poster_path"]
        result_data["genres"] = await get_genres(session, result["id"], "movie")
        poster_cache[query] = result_data
        return result_data

    print(f"❌ No match found: {query}")
    poster_cache[query] = result_data
    return result_data

async def process_programme(programme, session):
    title_element = programme.find("title")
    if title_element is None:
        return

    title = title_element.text.strip()
    channel_id = programme.get("channel")

    print(f"➡️ Processing: {title}")

    # Add channel logo
    logo_url = CHANNEL_LOGOS.get(channel_id)
    if logo_url:
        logo_el = ET.Element("icon")
        logo_el.set("src", logo_url)
        programme.insert(0, logo_el)
        print(f"🖼️ Channel Logo added: {logo_url}")

    # Only process targeted channels
    if channel_id not in TARGET_CHANNELS:
        return

    result = await search_tmdb(session, title)

    if result["portrait"]:
        poster_el = ET.SubElement(programme, "icon")
        poster_el.set("src", result["portrait"])
        print(f"✅ Poster added: {result['portrait']}")

    if result["genres"]:
        for genre in result["genres"]:
            genre_el = ET.SubElement(programme, "category")
            genre_el.text = genre
        print(f"🎯 Genres added: {', '.join(result['genres'])}")
    else:
        print(f"⚠️ No genres found for: {title}")

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    programmes = root.findall("programme")
    print(f"🔢 Total programmes: {len(programmes)}")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(p, session) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Updated EPG saved to {OUTPUT_FILE}")

    with open(CACHE_FILE, "w") as f:
        json.dump(poster_cache, f)
    print("💾 Poster & genre cache saved.")

if __name__ == "__main__":
    asyncio.run(main())
