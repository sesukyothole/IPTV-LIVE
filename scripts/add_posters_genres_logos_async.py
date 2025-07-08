import aiohttp
import asyncio
import os
import json
import xml.etree.ElementTree as ET

API_KEY = os.environ['TMDB_API_KEY']
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_INFO_MOVIE = "https://api.themoviedb.org/3/movie/"
TMDB_INFO_TV = "https://api.themoviedb.org/3/tv/"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

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

# Load or initialize cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

async def fetch_json(session, url, params):
    try:
        async with session.get(url, params=params) as response:
            return await response.json()
    except Exception as e:
        print(f"⚠️ Fetch error: {e}")
        return {}

async def get_genres(session, content_id, content_type):
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}"
    data = await fetch_json(session, url, {"api_key": API_KEY})
    return [g["name"] for g in data.get("genres", [])]

async def search_tmdb(session, title):
    if title in poster_cache:
        print(f"⚡ Cache hit: {title}")
        return poster_cache[title]

    print(f"🔍 Searching for poster: {title}")
    result = {"poster": None, "genres": []}

    tv_data = await fetch_json(session, TMDB_SEARCH_TV, {"api_key": API_KEY, "query": title})
    if tv_data.get("results"):
        item = tv_data["results"][0]
        if item.get("poster_path"):
            result["poster"] = TMDB_IMAGE_BASE + item["poster_path"]
        result["genres"] = await get_genres(session, item["id"], "tv")
        poster_cache[title] = result
        print(f"✅ TV Show Poster added: {title}")
        return result

    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE, {"api_key": API_KEY, "query": title})
    if movie_data.get("results"):
        item = movie_data["results"][0]
        if item.get("poster_path"):
            result["poster"] = TMDB_IMAGE_BASE + item["poster_path"]
        result["genres"] = await get_genres(session, item["id"], "movie")
        poster_cache[title] = result
        print(f"✅ Movie Poster added: {title}")
        return result

    print(f"❌ Poster not found: {title}")
    poster_cache[title] = result
    return result

def inject_channel_logos(root):
    for channel in root.findall("channel"):
        cid = channel.get("id")
        logo = CHANNEL_LOGOS.get(cid)
        if logo:
            existing = channel.find("icon")
            if existing is not None:
                channel.remove(existing)
            icon = ET.SubElement(channel, "icon")
            icon.set("src", logo)
            print(f"📺 Logo injected: {cid}")

async def process_programme(session, programme):
    channel_id = programme.get("channel")
    if channel_id not in TARGET_CHANNELS:
        return

    title_tag = programme.find("title")
    if title_tag is None:
        return

    title = title_tag.text.strip()
    data = await search_tmdb(session, title)

    # Remove all <icon> to prevent duplicates
    for icon in programme.findall("icon"):
        programme.remove(icon)

    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])

    for genre in data["genres"]:
        cat = ET.SubElement(programme, "category")
        cat.text = genre

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    inject_channel_logos(root)
    programmes = root.findall("programme")
    print(f"📃 Programmes to process: {len(programmes)}")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    with open(CACHE_FILE, "w") as f:
        json.dump(poster_cache, f)

    print(f"\n✅ Enrichment complete! Output: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
