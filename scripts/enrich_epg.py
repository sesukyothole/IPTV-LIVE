import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Channels you want to enrich
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

# Manual TMDb ID overrides for known titles
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

# TMDb genre ID to name mapping
TMDB_GENRES = {
    16: "Animation", 35: "Comedy", 10751: "Family", 18: "Drama", 10762: "Kids",
    10759: "Action & Adventure", 10765: "Sci-Fi & Fantasy", 9648: "Mystery",
    80: "Crime", 99: "Documentary", 10766: "Soap", 10763: "News", 10402: "Music"
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        return await resp.json()

async def get_tmdb_data(session, title):
    # Check for manual override first
    if title in MANUAL_ID_OVERRIDES:
        override = MANUAL_ID_OVERRIDES[title]
        url = f"{TMDB_BASE}/{override['type']}/{override['id']}"
        params = {"api_key": TMDB_API_KEY}
        data = await fetch_json(session, url, params)
        rating = await get_rating(session, override["type"], override["id"])
        return parse_tmdb_data(data, override["type"], rating)

    # Try movie search
    search = await fetch_json(session, f"{TMDB_BASE}/search/movie", {
        "api_key": TMDB_API_KEY, "query": title
    })
    if search.get("results"):
        movie = search["results"][0]
        rating = await get_rating(session, "movie", movie["id"])
        return parse_tmdb_data(movie, "movie", rating)

    # Try TV search
    search = await fetch_json(session, f"{TMDB_BASE}/search/tv", {
        "api_key": TMDB_API_KEY, "query": title
    })
    if search.get("results"):
        tv = search["results"][0]
        rating = await get_rating(session, "tv", tv["id"])
        return parse_tmdb_data(tv, "tv", rating)

    return None

def parse_tmdb_data(data, media_type, rating):
    genre_id = data.get("genre_ids", data.get("genres", []))
    genre_name = None
    if genre_id:
        gid = genre_id[0] if isinstance(genre_id[0], int) else genre_id[0].get("id", None)
        genre_name = TMDB_GENRES.get(gid, None)

    return {
        "title": data.get("title") or data.get("name"),
        "overview": data.get("overview", "").strip(),
        "poster": data.get("poster_path"),
        "genre": genre_name,
        "rating": rating,
        "year": (data.get("release_date") or data.get("first_air_date") or "")[:4]
    }

async def get_rating(session, media_type, tmdb_id):
    if media_type == "movie":
        data = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", {"api_key": TMDB_API_KEY})
        for result in data.get("results", []):
            if result["iso_3166_1"] == "US":
                for release in result["release_dates"]:
                    cert = release.get("certification")
                    if cert:
                        return cert
    else:
        data = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", {"api_key": TMDB_API_KEY})
        for result in data.get("results", []):
            if result["iso_3166_1"] == "US":
                return result.get("rating")
    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        print("⚠️ Skipped entry: No title")
        return

    title = title_el.text.strip()
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    print(f"📺 Processing: {title}")

    try:
        data = await get_tmdb_data(session, title)
        if not data:
            print(f"❌ No TMDb match for {title}")
            return

        # Update title with year
        if data["year"]:
            title_el.text = f"{data['title']} ({data['year']})"

        # Add description
        if data["overview"]:
            desc_el = programme.find("desc")
            if desc_el is None:
                desc_el = ET.SubElement(programme, "desc")
            desc_el.text = data["overview"]

        # Add poster
        if data["poster"]:
            icon_el = ET.SubElement(programme, "icon")
            icon_el.set("src", f"{TMDB_IMAGE_BASE}{data['poster']}")

        # Add genre
        if data["genre"]:
            genre_el = ET.SubElement(programme, "category")
            genre_el.text = data["genre"]

        # Add MPAA/TV rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]

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
