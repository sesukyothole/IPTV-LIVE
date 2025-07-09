import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

# Environment TMDb API key
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as an environment variable or 3rd argument.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Channels to enrich
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

# TMDb Genre Mapping
GENRE_MAP = {
    16: "Animation", 35: "Comedy", 18: "Drama", 10751: "Family", 28: "Action",
    12: "Adventure", 14: "Fantasy", 27: "Horror", 10765: "Sci-Fi & Fantasy",
    10759: "Action & Adventure", 99: "Documentary", 10770: "TV Movie",
    10762: "Kids", 10766: "Soap", 9648: "Mystery", 80: "Crime", 10402: "Music"
}

# Manual TMDb ID Overrides
MANUAL_ID_OVERRIDES = {
    "Jessie": {"type": "tv", "id": 38974},
    "Big City Greens": {"type": "tv", "id": 80587},
    "Kiff": {"type": "tv", "id": 127706},
    "Zombies": {"type": "movie", "id": 483980},
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id":585},
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

async def fetch_tmdb_data(session, media_type, tmdb_id):
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})

    rating = await (get_movie_rating(session, tmdb_id) if media_type == "movie" else get_tv_rating(session, tmdb_id))

    return {
        "title": data.get("title") or data.get("name"),
        "poster": TMDB_IMAGE_BASE + (data.get("poster_path") or ""),
        "description": data.get("overview", "").strip(),
        "genres": [g["name"] for g in data.get("genres", [])],
        "rating": rating,
        "year": (data.get("release_date") or data.get("first_air_date") or "0000")[:4]
    }

async def search_tmdb(session, title):
    for override_title in MANUAL_ID_OVERRIDES:
        if title.lower() == override_title.lower():
            override = MANUAL_ID_OVERRIDES[override_title]
            return await fetch_tmdb_data(session, override["type"], override["id"])

    # Fallback search
    params = {"api_key": TMDB_API_KEY, "query": title}
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        m = movie["results"][0]
        return await fetch_tmdb_data(session, "movie", m["id"])

    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        t = tv["results"][0]
        return await fetch_tmdb_data(session, "tv", t["id"])

    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")
    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"🔍 Enriching: {title}")

    try:
        data = await search_tmdb(session, title)
        if not data:
            print(f"❌ Not found: {title}")
            return

        # Add poster
        if data["poster"]:
            ET.SubElement(programme, "icon", src=data["poster"])
            print("🖼️ Poster added")

        # Add description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print("📝 Description added")

        # Add genres
        if data["genres"]:
            for g in data["genres"]:
                cat = ET.SubElement(programme, "category")
                cat.text = g
            print("🏷️ Genres added")

        # Add MPAA/TV rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            ET.SubElement(rating_el, "value").text = data["rating"]
            print(f"🎞️ Rating added: {data['rating']}")

        # Add year to title (Sparkle will show as (YYYY))
        if data["year"] and data["year"].isdigit():
            title_el.text = f"{title} ({data['year']})"
            print(f"📅 Year added: {data['year']}")

    except Exception as e:
        print(f"⚠️ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
