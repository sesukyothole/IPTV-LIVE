import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import sys

TARGET_CHANNELS = {"403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"}

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

GENRE_MAP = {
    # Will be populated at runtime from TMDb
    "movie": {},
    "tv": {}
}

def extract_program_year(programme):
    date_el = programme.find("date")
    if date_el is not None and date_el.text and len(date_el.text) >= 4:
        return date_el.text[:4]
    start = programme.get("start")
    if start and len(start) >= 4:
        return start[:4]
    return None

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def fetch_genre_maps(session):
    global GENRE_MAP
    for type_ in ["movie", "tv"]:
        data = await fetch_json(session, f"{TMDB_BASE}/genre/{type_}/list", {"api_key": TMDB_API_KEY})
        GENRE_MAP[type_] = {g["id"]: g["name"] for g in data.get("genres", [])}

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

async def enrich_with_tmdb_id(session, tmdb_id, type_):
    if type_ == "movie":
        details = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}", {"api_key": TMDB_API_KEY})
        rating = await get_movie_rating(session, tmdb_id)
    else:
        details = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}", {"api_key": TMDB_API_KEY})
        rating = await get_tv_rating(session, tmdb_id)

    return {
        "title": details.get("title") or details.get("name"),
        "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
        "description": details.get("overview", "").strip(),
        "genres": [GENRE_MAP[type_].get(g["id"]) for g in details.get("genres", [])],
        "rating": rating
    }

async def search_by_imdb(session, imdb_id):
    data = await fetch_json(session, f"{TMDB_BASE}/find/{imdb_id}", {
        "api_key": TMDB_API_KEY,
        "external_source": "imdb_id"
    })
    if data.get("movie_results"):
        return await enrich_with_tmdb_id(session, data["movie_results"][0]["id"], "movie")
    elif data.get("tv_results"):
        return await enrich_with_tmdb_id(session, data["tv_results"][0]["id"], "tv")
    return None

async def search_by_title(session, title, year=None):
    params = {"api_key": TMDB_API_KEY, "query": title}
    if year:
        params["year"] = year
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        details = movie["results"][0]
        return await enrich_with_tmdb_id(session, details["id"], "movie")

    params = {"api_key": TMDB_API_KEY, "query": title}
    if year:
        params["first_air_date_year"] = year
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        details = tv["results"][0]
        return await enrich_with_tmdb_id(session, details["id"], "tv")

    return None

def get_imdb_id(programme):
    for eid in programme.findall("episode-num"):
        if eid.attrib.get("system") == "imdb":
            return eid.text
    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None:
        return
    title = title_el.text.strip()
    year = extract_program_year(programme)
    imdb_id = get_imdb_id(programme)

    print(f"\n📺 Processing: {title} ({year or 'unknown'})")

    try:
        data = await search_by_imdb(session, imdb_id) if imdb_id else await search_by_title(session, title, year)

        if not data:
            print(f"❌ Not found: {title}")
            return

        # Poster
        if data["poster"]:
            icon = programme.find("icon")
            if icon is None:
                icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added.")

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print(f"📝 Description added.")

        # Genres
        if data["genres"]:
            for g in data["genres"]:
                if g:
                    cat = ET.SubElement(programme, "category")
                    cat.text = g
            print(f"🏷️ Genres added: {', '.join(g for g in data['genres'] if g)}")

        # MPAA Rating
        if data["rating"]:
            rating_el = programme.find("rating")
            if rating_el is None:
                rating_el = ET.SubElement(programme, "rating")
            value_el = rating_el.find("value")
            if value_el is None:
                value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ Rating added: {data['rating']}")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await fetch_genre_maps(session)
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async_imdb.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
