import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os
from aiohttp import ClientTimeout

# Load TMDb API Key
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Channels to enrich
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

# TMDb Genre ID to readable name
GENRE_MAP = {
    16: "Animation", 35: "Comedy", 10751: "Family", 10762: "Kids",
    18: "Drama", 28: "Action", 12: "Adventure", 10759: "Action & Adventure",
    10402: "Music", 99: "Documentary"
}

# Manual TMDb ID overrides
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

# Fetch TMDb JSON data
async def fetch_json(session, url, params):
    async with session.get(url, params=params) as res:
        return await res.json()

async def get_rating(session, media_type, tmdb_id):
    if media_type == "movie":
        url = f"{TMDB_BASE}/movie/{tmdb_id}/release_dates"
    else:
        url = f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings"

    data = await fetch_json(session, url, {"api_key": TMDB_API_KEY})
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "US":
            if media_type == "movie":
                for r in entry["release_dates"]:
                    cert = r.get("certification", "")
                    if cert:
                        return cert
            else:
                return entry.get("rating", "")
    return "NR"

async def get_tmdb_data(session, title):
    # Use manual override if available
    if title in MANUAL_ID_OVERRIDES:
        override = MANUAL_ID_OVERRIDES[title]
        media_type = override["type"]
        tmdb_id = override["id"]
        data = await fetch_json(session, f"{TMDB_BASE}/{media_type}/{tmdb_id}", {"api_key": TMDB_API_KEY})
        rating = await get_rating(session, media_type, tmdb_id)
        genres = data.get("genres", [])
        return {
            "title": data.get("title") or data.get("name"),
            "overview": data.get("overview", "").strip(),
            "poster": data.get("poster_path"),
            "year": (data.get("release_date") or data.get("first_air_date") or "")[:4],
            "genre": next((GENRE_MAP.get(g["id"]) for g in genres if g["id"] in GENRE_MAP), None),
            "rating": rating
        }

    # Try search (movie then TV)
    for mtype in ["movie", "tv"]:
        res = await fetch_json(session, f"{TMDB_BASE}/search/{mtype}", {"api_key": TMDB_API_KEY, "query": title})
        if res.get("results"):
            match = res["results"][0]
            return await get_tmdb_data(session, match["title"] if mtype == "movie" else match["name"])
    return None

# Process each <programme>
async def process_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None:
        print("⚠️ Skipping: No <title> tag found")
        return

    if not title_el.text or not title_el.text.strip():
        print("⚠️ Skipping: Empty <title> text")
        return

    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"📺 Processing: {title}")
    try:
        data = await get_tmdb_data(session, title)
        if not data:
            print(f"❌ No match for: {title}")
            return

        # Update title with year
        if data["year"]:
            title_el.text = f"{data['title']} ({data['year']})"

        # Add/replace description
        if data["overview"]:
            desc_el = programme.find("desc") or ET.SubElement(programme, "desc")
            desc_el.text = data["overview"]

        # Poster
        if data["poster"]:
            icon_el = ET.SubElement(programme, "icon")
            icon_el.set("src", f"{TMDB_IMAGE_BASE}{data['poster']}")

        # One readable genre
        if data["genre"]:
            cat_el = ET.SubElement(programme, "category")
            cat_el.text = data["genre"]

        # Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            val = ET.SubElement(rating_el, "value")
            val.text = data["rating"]

        await asyncio.sleep(0.25)  # avoid rate limit

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

# Main function
async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    timeout = ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

# CLI entry point
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
