import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403772", "403576"
}

GENRE_MAPPING = {
    16: "Animation", 35: "Comedy", 10751: "Family", 10762: "Kids",
    10759: "Action", 10765: "Sci-Fi & Fantasy", 18: "Drama", 27: "Horror",
    28: "Action", 10766: "Soap", 10402: "Music", 99: "Documentary",
    12: "Adventure", 14: "Fantasy"
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

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_movie_rating(session, movie_id, api_key):
    data = await fetch_json(session, f"{TMDB_BASE}/movie/{movie_id}/release_dates", {"api_key": api_key})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            for rel in entry["release_dates"]:
                cert = rel.get("certification", "")
                if cert:
                    return cert
    return "Not Rated"

async def get_tv_rating(session, tv_id, api_key):
    data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/content_ratings", {"api_key": api_key})
    for entry in data.get("results", []):
        if entry["iso_3166_1"] == "US":
            return entry.get("rating", "Not Rated")
    return "Not Rated"

async def get_tmdb_details(session, title, api_key):
    if title in MANUAL_ID_OVERRIDES:
        override = MANUAL_ID_OVERRIDES[title]
        if override["type"] == "movie":
            details = await fetch_json(session, f"{TMDB_BASE}/movie/{override['id']}", {"api_key": api_key})
            rating = await get_movie_rating(session, override["id"], api_key)
        else:
            details = await fetch_json(session, f"{TMDB_BASE}/tv/{override['id']}", {"api_key": api_key})
            rating = await get_tv_rating(session, override["id"], api_key)
    else:
        params = {"api_key": api_key, "query": title}
        movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
        if movie.get("results"):
            details = movie["results"][0]
            rating = await get_movie_rating(session, details["id"], api_key)
        else:
            tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
            if tv.get("results"):
                details = tv["results"][0]
                rating = await get_tv_rating(session, details["id"], api_key)
            else:
                return None

    return {
        "title": details.get("title") or details.get("name"),
        "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
        "description": details.get("overview", "").strip(),
        "genres": [GENRE_MAPPING.get(gid) for gid in details.get("genre_ids", []) if GENRE_MAPPING.get(gid)],
        "rating": rating,
        "year": (details.get("first_air_date") or details.get("release_date") or "")[:4]
    }

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n📺 Processing: {title}")

    try:
        data = await get_tmdb_details(session, title, TMDB_API_KEY)
        if not data:
            print(f"❌ No match found for: {title}")
            return

        # Poster
        if data["poster"]:
            icon = programme.find("icon")
            if icon is None:
                icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added for {title}")
        else:
            print(f"⚠️ No poster for {title}")

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print(f"📝 Description added for {title}")
        else:
            print(f"⚠️ No description for {title}")

        # Genres
        if data["genres"]:
            for g in data["genres"]:
                genre_el = ET.SubElement(programme, "category")
                genre_el.text = g
            print(f"🏷️ Genres added for {title}")
        else:
            print(f"⚠️ No genres for {title}")

        # MPAA Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            rating_el.set("system", "MPAA")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ MPAA Rating added for {title}: {data['rating']}")
        else:
            print(f"⚠️ No rating for {title}")

        # First Air Year for Kodi
        if data["year"]:
            date_el = programme.find("date")
            if date_el is None:
                date_el = ET.SubElement(programme, "date")
            date_el.text = data["year"]
            print(f"📆 Year added for {title}: {data['year']}")
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

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
