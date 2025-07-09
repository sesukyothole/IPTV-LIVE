import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os
from aiohttp import ClientTimeout

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# ✅ Target channels to enrich
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

# ✅ TMDb genre ID → name mapping
TMDB_GENRE_MAPPING = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western", 10759: "Action & Adventure",
    10762: "Kids", 10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics"
}

# ✅ Manual TMDb ID overrides for common mismatches
MANUAL_ID_OVERRIDES = {
    "Jessie": {"type": "tv", "id": 38974},
    "Big City Greens": {"type": "tv", "id": 80587},
    "Kiff": {"type": "tv", "id": 127706},
    "Zombies": {"type": "movie", "id": 483980},
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id": 585},
    "The Incredibles": {"type": "movie", "id": 9806}
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_movie_rating(session, movie_id):
    data = await fetch_json(session, f"{TMDB_BASE}/movie/{movie_id}/release_dates", {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            for rel in entry["release_dates"]:
                cert = rel.get("certification", "")
                if cert:
                    return cert
    return "NR"

async def get_tv_rating(session, tv_id):
    data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/content_ratings", {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            return entry.get("rating", "NR")
    return "NR"

async def fetch_tmdb_data(session, title):
    if title in MANUAL_ID_OVERRIDES:
        override = MANUAL_ID_OVERRIDES[title]
        tmdb_id = override["id"]
        media_type = override["type"]
        url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
        params = {"api_key": TMDB_API_KEY}
        data = await fetch_json(session, url, params)

        rating = await (get_movie_rating(session, tmdb_id) if media_type == "movie" else get_tv_rating(session, tmdb_id))
        return {
            "title": data.get("title") or data.get("name"),
            "overview": data.get("overview", "").strip(),
            "poster": TMDB_IMAGE_BASE + (data.get("poster_path") or ""),
            "genres": [TMDB_GENRE_MAPPING.get(g["id"]) for g in data.get("genres", []) if TMDB_GENRE_MAPPING.get(g["id"])],
            "rating": rating,
            "year": (data.get("release_date") or data.get("first_air_date") or "")[:4]
        }

    # No override: search TMDb
    params = {"api_key": TMDB_API_KEY, "query": title}
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        return await fetch_tmdb_data(session, movie["results"][0]["title"])

    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        return await fetch_tmdb_data(session, tv["results"][0]["name"])

    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or not title_el.text or not channel or channel not in TARGET_CHANNELS:
        return

    title_text = title_el.text.strip()
    print(f"📺 Processing: {title_text}")

    try:
        data = await fetch_tmdb_data(session, title_text)
        if not data:
            print(f"❌ No data for: {title_text}")
            return

        # Update title with year
        if data["year"]:
            title_el.text = f"{data['title']} ({data['year']})"

        # Description
        if data["overview"]:
            desc_el = programme.find("desc")
            if desc_el is None:
                desc_el = ET.SubElement(programme, "desc")
            desc_el.text = data["overview"]

        # Poster
        if data["poster"]:
            icon_el = ET.SubElement(programme, "icon")
            icon_el.set("src", data["poster"])

        # Genre (only 1)
        if data["genres"]:
            cat_el = ET.SubElement(programme, "category")
            cat_el.text = data["genres"][0]

        # Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]

        # Throttle to avoid hitting TMDb rate limit
        await asyncio.sleep(0.25)

    except Exception as e:
        print(f"❌ Error processing {title_text}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    timeout = ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
