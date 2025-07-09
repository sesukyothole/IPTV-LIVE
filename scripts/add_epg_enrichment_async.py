import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import sys

# Target channel IDs to filter which programmes to enrich
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Map TMDb genre IDs to names
TMDB_GENRE_MAP = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics"
}

# Manual TMDb ID overrides for exact matching of known tricky titles
MANUAL_ID_OVERRIDES = {
    "Disney's Jessie": {"type": "tv", "id": 38974},      
    "Big City Greens": {"type": "tv", "id": 80587},         
    "Kiff": {"type": "tv", "id": 127706},                   
    "Zombies": {"type": "movie", "id": 483980},   
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id": 585}
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
    return "Not Rated"

async def get_tv_rating(session, tv_id):
    data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/content_ratings", {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            return entry.get("rating", "Not Rated")
    return "Not Rated"

async def search_tmdb(session, title):
    # Check manual ID overrides first
    if title in MANUAL_ID_OVERRIDES:
        entry = MANUAL_ID_OVERRIDES[title]
        id_type = entry["type"]
        id_value = entry["id"]

        if id_type == "movie":
            details = await fetch_json(session, f"{TMDB_BASE}/movie/{id_value}", {"api_key": TMDB_API_KEY})
            rating = await get_movie_rating(session, id_value)
            genres = [g['id'] for g in details.get("genres", [])]
            return {
                "title": details.get("title"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [str(gid) for gid in genres],
                "rating": rating
            }
        else:
            details = await fetch_json(session, f"{TMDB_BASE}/tv/{id_value}", {"api_key": TMDB_API_KEY})
            rating = await get_tv_rating(session, id_value)
            genres = [g['id'] for g in details.get("genres", [])]
            return {
                "title": details.get("name"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [str(gid) for gid in genres],
                "rating": rating
            }

    # Fallback to search by title (TV first, then movies)
    params = {"api_key": TMDB_API_KEY, "query": title}

    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        details = tv["results"][0]
        rating = await get_tv_rating(session, details["id"])
        return {
            "title": details.get("name"),
            "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
            "description": details.get("overview", "").strip(),
            "genres": [str(gid) for gid in details.get("genre_ids", [])],
            "rating": rating
        }

    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        details = movie["results"][0]
        rating = await get_movie_rating(session, details["id"])
        return {
            "title": details.get("title"),
            "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
            "description": details.get("overview", "").strip(),
            "genres": [str(gid) for gid in details.get("genre_ids", [])],
            "rating": rating
        }

    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n📺 Processing: {title}")

    try:
        data = await search_tmdb(session, title)
        if not data:
            print(f"❌ No match found for: {title}")
            return

        # Poster
        if data["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added for {title}")

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print(f"📝 Description added for {title}")

        # Genres (convert genre IDs to names)
        if data["genres"]:
            for gid_str in data["genres"]:
                gid = int(gid_str)
                genre_name = TMDB_GENRE_MAP.get(gid, f"Unknown ({gid})")
                genre_el = ET.SubElement(programme, "category")
                genre_el.text = genre_name
            print(f"🏷️ Genres added for {title}")

        # MPAA Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ MPAA Rating added for {title}: {data['rating']}")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

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
