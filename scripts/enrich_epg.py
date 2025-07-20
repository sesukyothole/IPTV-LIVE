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

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "403847", "403772", "403576", "403926",
    "403461"
}

# Manual TMDb overrides
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
    "Moana": {"type": "movie", "id": 277834},
    "Modern Family": {"type": "tv", "id": 1421},
    "Henry Danger": {"type": "tv", "id": 61852},
    "The Really Loud House": {"type": "tv", "id": 211779}
}

TMDB_GENRES = {
    16: "Animation",
    35: "Comedy",
    10751: "Family",
    10762: "Kids",
    18: "Drama",
    28: "Action",
    10759: "Adventure",
    12: "Adventure",
    14: "Fantasy",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    878: "Sci-Fi",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics"
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_details(session, content_type, content_id):
    return await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}", {"api_key": TMDB_API_KEY})

async def get_credits(session, content_type, content_id):
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/credits", {"api_key": TMDB_API_KEY})
    cast = [member["name"] for member in data.get("cast", [])[:3]]  # Top 3
    directors = [crew["name"] for crew in data.get("crew", []) if crew.get("job") == "Director"]
    return cast, directors[0] if directors else None

async def get_rating(session, content_type, content_id):
    endpoint = "release_dates" if content_type == "movie" else "content_ratings"
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/{endpoint}", {"api_key": TMDB_API_KEY})
    results = data.get("results", [])
    for entry in results:
        if entry.get("iso_3166_1") == "US":
            if content_type == "movie":
                for rel in entry.get("release_dates", []):
                    cert = rel.get("certification")
                    if cert:
                        return cert
            else:
                return entry.get("rating")
    return "Not Rated"

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}
    movie_data = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie_data.get("results"):
        result = movie_data["results"][0]
        rating = await get_rating(session, "movie", result["id"])
        cast, director = await get_credits(session, "movie", result["id"])
        return {
            "title": result.get("title"),
            "poster": TMDB_IMAGE_BASE + (result.get("poster_path") or ""),
            "description": result.get("overview", "").strip(),
            "genres": [TMDB_GENRES.get(gid) for gid in result.get("genre_ids", []) if TMDB_GENRES.get(gid)],
            "year": result.get("release_date", "")[:4],
            "rating": rating,
            "cast": cast,
            "director": director
        }

    tv_data = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv_data.get("results"):
        result = tv_data["results"][0]
        rating = await get_rating(session, "tv", result["id"])
        cast, director = await get_credits(session, "tv", result["id"])
        return {
            "title": result.get("name"),
            "poster": TMDB_IMAGE_BASE + (result.get("poster_path") or ""),
            "description": result.get("overview", "").strip(),
            "genres": [TMDB_GENRES.get(gid) for gid in result.get("genre_ids", []) if TMDB_GENRES.get(gid)],
            "year": result.get("first_air_date", "")[:4],
            "rating": rating,
            "cast": cast,
            "director": director
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
        if title in MANUAL_ID_OVERRIDES:
            override = MANUAL_ID_OVERRIDES[title]
            details = await get_details(session, override["type"], override["id"])
            rating = await get_rating(session, override["type"], override["id"])
            cast, director = await get_credits(session, override["type"], override["id"])
            data = {
                "title": details.get("name") or details.get("title"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [TMDB_GENRES.get(gid) for gid in [g["id"] for g in details.get("genres", [])] if TMDB_GENRES.get(gid)],
                "year": (details.get("first_air_date") or details.get("release_date") or "")[:4],
                "rating": rating,
                "cast": cast,
                "director": director
            }
        else:
            data = await search_tmdb(session, title)

        if not data:
            print(f"❌ No match found for: {title}")
            return

        # Poster
        if data["poster"]:
            icon = programme.find("icon")
            if icon is None:
                icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]

        # Genres
        if data["genres"]:
            for g in data["genres"]:
                genre_el = ET.SubElement(programme, "category")
                genre_el.text = g

        # Year
        if data["year"]:
            date_el = programme.find("date")
            if date_el is None:
                date_el = ET.SubElement(programme, "date")
            date_el.text = data["year"]

        # Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]

        # Cast
        if data.get("cast"):
            credits_el = programme.find("credits")
            if credits_el is None:
                credits_el = ET.SubElement(programme, "credits")
            for actor in data["cast"]:
                ET.SubElement(credits_el, "actor").text = actor

        # Director
        if data.get("director"):
            credits_el = programme.find("credits")
            if credits_el is None:
                credits_el = ET.SubElement(programme, "credits")
            ET.SubElement(credits_el, "director").text = data["director"]

        print(f"✅ Done: {title}")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py guide.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))