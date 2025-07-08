import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json
import sys

TMDB_API_KEY = os.environ['TMDB_API_KEY']
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_MOVIE_DETAILS = "https://api.themoviedb.org/3/movie/{id}"
TMDB_TV_DETAILS = "https://api.themoviedb.org/3/tv/{id}"

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

CACHE = {}
GENRE_MAP = {}  # optional future caching of genre IDs

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as response:
            return await response.json()

async def fetch_rating(session, content_id, content_type):
    url = TMDB_MOVIE_DETAILS if content_type == "movie" else TMDB_TV_DETAILS
    url = url.format(id=content_id)
    try:
        json_data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
        release_info = json_data.get("release_dates" if content_type == "movie" else "content_ratings", {})
        results = release_info.get("results", [])
        for entry in results:
            if entry.get("iso_3166_1") == "US":
                ratings = entry.get("release_dates" if content_type == "movie" else "rating", [])
                if isinstance(ratings, list):
                    for r in ratings:
                        cert = r.get("certification")
                        if cert:
                            return cert
                elif isinstance(ratings, str):
                    return ratings
    except:
        pass
    return "N/A"

def resolve_genres(genre_ids):
    # Basic static genre mapping
    genre_dict = {
        16: "Animation", 35: "Comedy", 80: "Crime", 99: "Documentary", 18: "Drama",
        10751: "Family", 14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
        9648: "Mystery", 10749: "Romance", 878: "Science Fiction", 10770: "TV Movie",
        53: "Thriller", 10752: "War", 37: "Western"
    }
    return [genre_dict.get(gid, str(gid)) for gid in genre_ids]

async def search_tmdb(session, title):
    if title in CACHE:
        return CACHE[title]

    result_data = {"poster": None, "genres": [], "description": None, "rating": "N/A"}

    for url, content_type in [(TMDB_SEARCH_TV_URL, "tv"), (TMDB_SEARCH_MOVIE_URL, "movie")]:
        search = await fetch_json(session, url, {"api_key": TMDB_API_KEY, "query": title})
        results = search.get("results", [])
        if results:
            item = results[0]
            poster_path = item.get("poster_path")
            result_data["poster"] = TMDB_IMAGE_URL + poster_path if poster_path else None
            result_data["description"] = item.get("overview")
            result_data["genres"] = resolve_genres(item.get("genre_ids", []))
            result_data["rating"] = await fetch_rating(session, item.get("id"), content_type)
            break

    CACHE[title] = result_data
    return result_data

async def process_programme(session, programme):
    channel = programme.get("channel")
    title_el = programme.find("title")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n🎬 {title}")

    data = await search_tmdb(session, title)

    if channel in CHANNEL_LOGOS:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", CHANNEL_LOGOS[channel])
        print("🏷️ Channel logo added.")

    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print("🖼️ Poster added.")
    else:
        print("🚫 No poster found.")

    if data["genres"]:
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🎭 Genres added: {', '.join(data['genres'])}")
    else:
        print("🚫 No genres found.")

    if data["description"]:
        desc = ET.SubElement(programme, "desc")
        desc.text = data["description"]
        print("📝 Description added.")
    else:
        print("🚫 No description found.")

    if data["rating"] and data["rating"] != "N/A":
        rating_el = ET.SubElement(programme, "rating")
        rating_val = ET.SubElement(rating_el, "value")
        rating_val.text = f"MPAA:{data['rating']}"
        print(f"🔞 Rating added: MPAA:{data['rating']}")
    else:
        print("🚫 No rating found.")

async def enrich_epg(input_path, output_path):
    tree = ET.parse(input_path)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG written to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_genres_logos_descriptions_ratings_async.py input.xml output.xml")
    else:
        asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
