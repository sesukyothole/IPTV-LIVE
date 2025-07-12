import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os

# Load TMDb API key
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# Only enrich these channels
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
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
    "The Incredibles": {"type": "movie", "id": 9806},
    "SpongeBob SquarePants": {"type": "tv", "id": 387},
    "Peppa Pig": {"type": "tv", "id": 12225},
    "PAW Patrol": {"type": "tv", "id": 57532},
    "Rubble & Crew": {"type": "tv", "id": 214875},
    "Gabby's Dollhouse": {"type": "tv", "id": 111474},
    "black-ish": {"type": "tv", "id": 61381},
    "Phineas and Ferb": {"type": "tv", "id": 1877},
    "The Amazing World of Gumball": {"type": "tv", "id": 37606},
    "Win or Lose": {"type": "tv", "id": 114500},
    "Teen Titans Go!": {"type": "tv", "id": 45140},
    "Bob's Burgers": {"type": "tv", "id": 32726},
    "Friends": {"type": "tv", "id": 1668},
    "Primos": {"type": "tv", "id": 204139},
    "DuckTales": {"type": "tv", "id": 72350}
}

# Map TMDb genre IDs to names
TMDB_GENRES = {
    16: "Animation", 35: "Comedy", 10751: "Family", 18: "Drama",
    10762: "Kids", 10759: "Action & Adventure", 10765: "Sci-Fi & Fantasy",
    9648: "Mystery", 80: "Crime", 99: "Documentary", 10766: "Soap",
    10763: "News", 10402: "Music"
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_rating(session, media_type, tmdb_id):
    if media_type == "movie":
        data = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", {"api_key": TMDB_API_KEY})
        for entry in data.get("results", []):
            if entry["iso_3166_1"] == "US":
                for release in entry.get("release_dates", []):
                    cert = release.get("certification")
                    if cert:
                        return cert
    else:
        data = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", {"api_key": TMDB_API_KEY})
        for entry in data.get("results", []):
            if entry["iso_3166_1"] == "US":
                return entry.get("rating")
    return None

async def get_tmdb_data(session, title):
    if title in MANUAL_ID_OVERRIDES:
        override = MANUAL_ID_OVERRIDES[title]
        tmdb_id, media_type = override["id"], override["type"]
        data = await fetch_json(session, f"{TMDB_BASE}/{media_type}/{tmdb_id}", {"api_key": TMDB_API_KEY})
        rating = await get_rating(session, media_type, tmdb_id)
    else:
        # Search movie
        search = await fetch_json(session, f"{TMDB_BASE}/search/movie", {"api_key": TMDB_API_KEY, "query": title})
        if search.get("results"):
            result = search["results"][0]
            media_type = "movie"
            tmdb_id = result["id"]
            data = result
            rating = await get_rating(session, media_type, tmdb_id)
        else:
            # Search TV
            search = await fetch_json(session, f"{TMDB_BASE}/search/tv", {"api_key": TMDB_API_KEY, "query": title})
            if search.get("results"):
                result = search["results"][0]
                media_type = "tv"
                tmdb_id = result["id"]
                data = result
                rating = await get_rating(session, media_type, tmdb_id)
            else:
                return None

    genre_ids = data.get("genre_ids", [])[0:1] if "genre_ids" in data else [g.get("id") for g in data.get("genres", [])]
    genre = TMDB_GENRES.get(genre_ids[0]) if genre_ids else None
    return {
        "title": data.get("title") or data.get("name"),
        "overview": data.get("overview", "").strip(),
        "poster": f"{TMDB_IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None,
        "genre": genre,
        "rating": rating,
        "year": (data.get("release_date") or data.get("first_air_date") or "")[:4]
    }

async def process_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        return
    title = title_el.text.strip()
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    print(f"\n📺 Processing: {title}")
    try:
        data = await get_tmdb_data(session, title)
        if not data:
            print(f"❌ No TMDb match found for: {title}")
            return

        # Title + Year
        if data["year"]:
            title_el.text = f"{data['title']} ({data['year']})"
            print(f"📅 Year added for {title}: {data['year']}")
        else:
            print(f"⚠️ No year found for {title}")

        # Description
        if data["overview"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["overview"]
            print(f"📝 Description added for {title}")
        else:
            print(f"⚠️ No description found for {title}")

        # Poster
        if data["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added for {title}")
        else:
            print(f"⚠️ No poster found for {title}")

        # Genre
        if data["genre"]:
            genre_el = ET.SubElement(programme, "category")
            genre_el.text = data["genre"]
            print(f"🏷️ Genre added for {title}: {data['genre']}")
        else:
            print(f"⚠️ No genre found for {title}")

        # MPAA Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ MPAA Rating added for {title}: {data['rating']}")
        else:
            print(f"⚠️ No MPAA Rating found for {title}")

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
