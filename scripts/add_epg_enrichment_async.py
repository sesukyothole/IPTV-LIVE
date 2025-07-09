import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

# TMDb Setup
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Only enrich these channels
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

# Sparkle TV expects age rating like this: "TV-PG" or "PG-13"
async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        return await resp.json()

async def get_movie_rating(session, movie_id):
    data = await fetch_json(session, f"{TMDB_BASE}/movie/{movie_id}/release_dates", {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            for rel in entry["release_dates"]:
                cert = rel.get("certification", "")
                if cert:
                    return cert
    return None

async def get_tv_rating(session, tv_id):
    data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/content_ratings", {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            return entry.get("rating")
    return None

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}

    # Try movie first
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        m = movie["results"][0]
        rating = await get_movie_rating(session, m["id"])
        return {
            "type": "movie",
            "title": m.get("title"),
            "poster": TMDB_IMAGE_BASE + m.get("poster_path") if m.get("poster_path") else None,
            "description": m.get("overview", "").strip(),
            "genres": [GENRE_MAP.get(gid) for gid in m.get("genre_ids", []) if GENRE_MAP.get(gid)],
            "rating": rating
        }

    # Try TV show
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        t = tv["results"][0]
        rating = await get_tv_rating(session, t["id"])
        return {
            "type": "tv",
            "title": t.get("name"),
            "poster": TMDB_IMAGE_BASE + t.get("poster_path") if t.get("poster_path") else None,
            "description": t.get("overview", "").strip(),
            "genres": [GENRE_MAP.get(gid) for gid in t.get("genre_ids", []) if GENRE_MAP.get(gid)],
            "rating": rating
        }

    return None

async def enrich_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None:
        return
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"📺 Processing: {title}")

    try:
        info = await search_tmdb(session, title)
        if not info:
            print(f"❌ No match found for: {title}")
            return

        # Add poster
        if info["poster"]:
            ET.SubElement(programme, "icon", {"src": info["poster"]})
            print(f"🖼️ Poster added")

        # Add description
        if info["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = info["description"]
            print(f"📝 Description added")

        # Add genre
        if info["genres"]:
            for g in info["genres"]:
                cat = ET.SubElement(programme, "category")
                cat.text = g
            print(f"🏷️ Genres added")

        # Add rating in Sparkle format
        if info["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = info["rating"]
            print(f"🔞 Rating added: {info['rating']}")

    except Exception as e:
        print(f"⚠️ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(enrich_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
