import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import json

TMDB_API_KEY = os.environ['TMDB_API_KEY']
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_DETAILS_TV = "https://api.themoviedb.org/3/tv/{id}"
TMDB_DETAILS_MOVIE = "https://api.themoviedb.org/3/movie/{id}"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Static genre ID mappings from TMDb (partial list; you can extend)
GENRE_ID_MAP = {
    16: "Animation", 35: "Comedy", 18: "Drama", 10751: "Family", 10762: "Kids",
    10759: "Action & Adventure", 9648: "Mystery", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics", 37: "Western",
    28: "Action", 12: "Adventure", 80: "Crime", 99: "Documentary",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    878: "Science Fiction", 53: "Thriller", 10749: "Romance"
}

CACHE_FILE = "poster_genre_cache.json"

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        CACHE = json.load(f)
else:
    CACHE = {}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        return await resp.json()

async def fetch_rating(session, content_id, media_type):
    url = TMDB_DETAILS_TV if media_type == "tv" else TMDB_DETAILS_MOVIE
    url = url.format(id=content_id)
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})

    if media_type == "movie":
        for result in data.get("release_dates", {}).get("results", []):
            if result.get("iso_3166_1") == "US":
                for entry in result.get("release_dates", []):
                    if entry.get("certification"):
                        return entry["certification"]
    else:
        for entry in data.get("content_ratings", {}).get("results", []):
            if entry.get("iso_3166_1") == "US":
                return entry.get("rating")
    return "N/A"

def resolve_genres(genre_ids):
    return [GENRE_ID_MAP.get(gid, f"Genre {gid}") for gid in genre_ids]

async def search_tmdb(session, title):
    if title in CACHE:
        print(f"⚡ Cache hit for: {title}")
        return CACHE[title]

    print(f"🎯 Searching TMDB: {title}")
    result_data = {"poster": None, "genres": [], "description": None, "rating": "N/A"}

    # Try TV first
    tv_resp = await fetch_json(session, TMDB_SEARCH_TV_URL, {"api_key": TMDB_API_KEY, "query": title})
    tv_results = tv_resp.get("results", [])
    if tv_results:
        show = tv_results[0]
        result_data["poster"] = TMDB_IMAGE_URL + show.get("poster_path", "")
        result_data["genres"] = resolve_genres(show.get("genre_ids", []))
        result_data["description"] = show.get("overview")
        result_data["rating"] = await fetch_rating(session, show["id"], "tv")
        CACHE[title] = result_data
        return result_data

    # Try Movie
    mv_resp = await fetch_json(session, TMDB_SEARCH_MOVIE_URL, {"api_key": TMDB_API_KEY, "query": title})
    mv_results = mv_resp.get("results", [])
    if mv_results:
        movie = mv_results[0]
        result_data["poster"] = TMDB_IMAGE_URL + movie.get("poster_path", "")
        result_data["genres"] = resolve_genres(movie.get("genre_ids", []))
        result_data["description"] = movie.get("overview")
        result_data["rating"] = await fetch_rating(session, movie["id"], "movie")
        CACHE[title] = result_data
        return result_data

    print(f"❌ No TMDB result found for: {title}")
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

    # Poster
    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print(f"🖼️ Poster added: {data['poster']}")
    else:
        print("❌ No poster found")

    # Genres
    if data["genres"]:
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🏷️ Genres added: {', '.join(data['genres'])}")
    else:
        print("❌ No genres found")

    # Description
    if data["description"]:
        desc = ET.SubElement(programme, "desc")
        desc.text = data["description"]
        print("📝 Description added")
    else:
        print("❌ No description found")

    # Rating
    if data["rating"] and data["rating"] != "N/A":
        rating_el = ET.SubElement(programme, "rating")
        value = ET.SubElement(rating_el, "value")
        value.text = data["rating"]
        print(f"🔞 Rating added: {data['rating']}")
    else:
        print("❌ No rating found")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG written to {output_file}")

    with open(CACHE_FILE, "w") as f:
        json.dump(CACHE, f)

if __name__ == "__main__":
    import sys
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
