import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

# TMDb API key from GitHub secrets or CLI arg
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

# --- CONFIG ---
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403772", "403576"
}

TMDB_GENRE_MAP = {
    16: "Animation", 35: "Comedy", 18: "Drama", 10751: "Family", 10762: "Kids",
    10759: "Action & Adventure", 9648: "Mystery", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics", 99: "Documentary",
    28: "Action", 12: "Adventure", 14: "Fantasy", 27: "Horror", 10402: "Music",
    878: "Science Fiction", 53: "Thriller", 80: "Crime", 36: "History",
    37: "Western", 10770: "TV Movie", 10749: "Romance"
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
    "The Incredibles": {"type": "movie", "id": 9806},
    "SpongeBob SquarePants": {"type": "tv", "id": 387},
    "Peppa Pig": {"type": "tv", "id": 12225},
    "PAW Patrol": {"type": "tv", "id": 57532},
    "Rubble & Crew": {"type": "tv", "id": 214875},
    "Gabby's Dollhouse": {"type": "tv", "id": 111474},
    "black-ish": {"type": "tv", "id": 61381},
    "Phineas and Ferb": {"type": "tv", "id": 1877},
    "Win or Lose": {"type": "tv", "id": 114500},
    "Friends": {"type": "tv", "id": 1668},
    "Primos": {"type": "tv", "id": 204139},
    "DuckTales": {"type": "tv", "id": 72350},
    "Mulan": {"type": "movie", "id": 337401},
    "Moana": {"type": "movie", "id": 277834}
}

# --- FETCH HELPERS ---

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_rating(session, content_type, tmdb_id):
    if content_type == "movie":
        data = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", {"api_key": TMDB_API_KEY})
        for entry in data.get("results", []):
            if entry["iso_3166_1"] == "US":
                for rel in entry["release_dates"]:
                    cert = rel.get("certification")
                    if cert:
                        return cert
    else:
        data = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", {"api_key": TMDB_API_KEY})
        for entry in data.get("results", []):
            if entry["iso_3166_1"] == "US":
                return entry.get("rating")
    return "NR"

async def get_details(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        m = movie["results"][0]
        rating = await get_rating(session, "movie", m["id"])
        return {
            "type": "movie",
            "poster": TMDB_IMAGE_BASE + m["poster_path"] if m.get("poster_path") else None,
            "desc": m.get("overview", "").strip(),
            "genres": [TMDB_GENRE_MAP.get(gid) for gid in m.get("genre_ids", []) if gid in TMDB_GENRE_MAP],
            "year": m.get("release_date", "")[:4],
            "rating": f"MPAA:{rating}"
        }

    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        t = tv["results"][0]
        rating = await get_rating(session, "tv", t["id"])
        return {
            "type": "tv",
            "poster": TMDB_IMAGE_BASE + t["poster_path"] if t.get("poster_path") else None,
            "desc": t.get("overview", "").strip(),
            "genres": [TMDB_GENRE_MAP.get(gid) for gid in t.get("genre_ids", []) if gid in TMDB_GENRE_MAP],
            "year": t.get("first_air_date", "")[:4],
            "rating": f"MPAA:{rating}"
        }

    return None

# --- MAIN ENRICHMENT FUNCTION ---

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")
    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return
    title = title_el.text.strip()
    print(f"\n📺 Processing: {title}")
    try:
        # Use override if available
        if title in MANUAL_ID_OVERRIDES:
            override = MANUAL_ID_OVERRIDES[title]
            details = await fetch_json(session, f"{TMDB_BASE}/{override['type']}/{override['id']}", {"api_key": TMDB_API_KEY})
            rating = await get_rating(session, override["type"], override["id"])
            genres = details.get("genres", [])
            genre_names = [g["name"] for g in genres if "name" in g]
            poster = TMDB_IMAGE_BASE + details.get("poster_path", "") if details.get("poster_path") else None
            desc = details.get("overview", "").strip()
            year = details.get("first_air_date", "")[:4] if override["type"] == "tv" else details.get("release_date", "")[:4]
            rating = f"MPAA:{rating}"
        else:
            data = await get_details(session, title)
            if not data:
                print(f"❌ No TMDb match for: {title}")
                return
            poster, desc, genre_names, year, rating = data["poster"], data["desc"], data["genres"], data["year"], data["rating"]

        # Poster
        if poster:
            ET.SubElement(programme, "icon", {"src": poster})
            print(f"🖼️ Poster added for {title}")
        else:
            print(f"⚠️ No poster for {title}")

        # Description
        if desc:
            desc_el = programme.find("desc") or ET.SubElement(programme, "desc")
            desc_el.text = desc
            print(f"📝 Description added for {title}")
        else:
            print(f"⚠️ No description for {title}")

        # Genres
        if genre_names:
            for g in genre_names:
                ET.SubElement(programme, "category").text = g
            print(f"🏷️ Genres added for {title}: {', '.join(genre_names)}")
        else:
            print(f"⚠️ No genre for {title}")

        # Rating
        if rating:
            r_el = ET.SubElement(programme, "rating")
            ET.SubElement(r_el, "value").text = rating
            print(f"🎞️ Rating added for {title}: {rating}")
        else:
            print(f"⚠️ No rating for {title}")

        # Year (Kodi/SparkleTV compatibility)
        if year:
            ET.SubElement(programme, "premiere").text = f"{year}-01-01"
            print(f"📅 Year added for {title}: {year}")
        else:
            print(f"⚠️ No year for {title}")

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

# --- ENTRYPOINT ---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
