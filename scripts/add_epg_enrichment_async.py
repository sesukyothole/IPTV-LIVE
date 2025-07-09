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
    "403655", "8359", "403847", "403461", "403576"
}

# Force-corrected titles for edge cases
FORCED_MATCHES = {
    "disney's zombies": {"title": "Zombies", "year": 2018, "type": "movie"},
    "zombies": {"title": "Zombies", "year": 2018, "type": "movie"},
    "monsters inc": {"title": "Monsters, Inc.", "year": 2001, "type": "movie"},
    "disney and pixar's monsters inc": {"title": "Monsters, Inc.", "year": 2001, "type": "movie"}
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

async def search_tmdb(session, title, api_key):
    title_key = title.lower().strip()
    forced = FORCED_MATCHES.get(title_key)

    if forced:
        params = {"api_key": api_key, "query": forced["title"], "year": forced["year"]}
        if forced["type"] == "movie":
            results = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
        else:
            results = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    else:
        params = {"api_key": api_key, "query": title}
        results = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
        if not results.get("results"):
            results = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)

    show = results["results"][0] if results.get("results") else None
    if not show:
        return None

    # Determine if it is TV or movie
    is_movie = "title" in show
    tmdb_id = show["id"]
    media_type = "movie" if is_movie else "tv"

    # Fetch details
    details = await fetch_json(session, f"{TMDB_BASE}/{media_type}/{tmdb_id}", {"api_key": api_key})

    # Rating
    rating = await (get_movie_rating(session, tmdb_id, api_key) if is_movie else get_tv_rating(session, tmdb_id, api_key))

    return {
        "title": details.get("title") or details.get("name"),
        "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
        "description": details.get("overview", "").strip(),
        "genres": [g["name"] for g in details.get("genres", [])],
        "rating": rating or "Not Rated"
    }

async def process_programme(session, programme):
    title_el = programme.find("title")
    if not title_el:
        return

    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n🎬 Processing: {title}")

    try:
        data = await search_tmdb(session, title, TMDB_API_KEY)
        if not data:
            print(f"❌ TMDb match failed for: {title}")
            return

        # Poster
        if data["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added")
        else:
            print(f"❌ No poster")

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print(f"📝 Description added")
        else:
            print(f"❌ No description")

        # Genres
        if data["genres"]:
            for genre in data["genres"]:
                genre_el = ET.SubElement(programme, "category")
                genre_el.text = genre
            print(f"🏷️ Genres: {', '.join(data['genres'])}")
        else:
            print("❌ No genres")

        # MPAA Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ MPAA Rating: {data['rating']}")
        else:
            print(f"❌ No MPAA Rating")

        print(f"✅ Enrichment complete for: {title}")

    except Exception as e:
        print(f"❌ Error on {title}: {e}")

async def enrich_epg(input_path, output_path):
    tree = ET.parse(input_path)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"\n📁 EPG saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async_strict.py epg.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
