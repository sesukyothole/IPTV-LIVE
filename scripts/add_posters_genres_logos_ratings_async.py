import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

# TMDb API
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

# Target channels (your 10 specific ones)
TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Cache file
CACHE_FILE = "poster_genre_rating_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        CACHE = json.load(f)
else:
    CACHE = {}

async def fetch_json(session, url, params):
    try:
        with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"❌ HTTP {response.status} for URL: {response.url}")
                    return {}
                return await response.json()
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return {}

async def search_tmdb(session, title):
    if title in CACHE:
        return CACHE[title]

    print(f"🔍 Searching TMDb for: {title}")
    result = {"poster": None, "genres": [], "rating": "N/A"}

    # TV Show search
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", {"api_key": TMDB_API_KEY, "query": title})
    if tv.get("results"):
        show = tv["results"][0]
        result["poster"] = TMDB_IMAGE + show["poster_path"] if show.get("poster_path") else None

        # Genres
        detail = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}", {"api_key": TMDB_API_KEY})
        result["genres"] = [g["name"] for g in detail.get("genres", [])]

        # Age rating
        ratings = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}/content_ratings", {"api_key": TMDB_API_KEY})
        for r in ratings.get("results", []):
            if r.get("iso_3166_1") == "US":
                result["rating"] = r.get("rating", "N/A")
        CACHE[title] = result
        return result

    # Movie search
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", {"api_key": TMDB_API_KEY, "query": title})
    if movie.get("results"):
        m = movie["results"][0]
        result["poster"] = TMDB_IMAGE + m["poster_path"] if m.get("poster_path") else None

        # Genres
        detail = await fetch_json(session, f"{TMDB_BASE}/movie/{m['id']}", {"api_key": TMDB_API_KEY})
        result["genres"] = [g["name"] for g in detail.get("genres", [])]

        # Age rating
        ratings = await fetch_json(session, f"{TMDB_BASE}/movie/{m['id']}/release_dates", {"api_key": TMDB_API_KEY})
        for r in ratings.get("results", []):
            if r.get("iso_3166_1") == "US":
                for rel in r.get("release_dates", []):
                    if rel.get("certification"):
                        result["rating"] = rel["certification"]
                        break
        CACHE[title] = result
        return result

    print(f"⚠️ No match found for {title}")
    CACHE[title] = result
    return result

async def process_programme(session, programme):
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        return

    title = title_el.text.strip()
    print(f"➡️ Processing: {title}")
    data = await search_tmdb(session, title)

    # Poster
    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print(f"✅ Poster added: {data['poster']}")
    else:
        print(f"⚠️ No poster for {title}")

    # Genres
    if data["genres"]:
        for genre in data["genres"]:
            g = ET.SubElement(programme, "category")
            g.text = genre
        print(f"🎯 Genres added: {', '.join(data['genres'])}")
    else:
        print(f"⚠️ No genres for {title}")

    # Age rating
    rating = data.get("rating", "N/A")
    if rating and rating != "N/A":
        age = ET.SubElement(programme, "rating")
        value = ET.SubElement(age, "value")
        value.text = rating
        print(f"🔞 Rating added: {rating}")
    else:
        print(f"⚠️ No rating for {title}")

async def enrich_epg(epg_path, output_path):
    tree = ET.parse(epg_path)
    root = tree.getroot()
    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)

    # Save output EPG
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG written to {output_path}")

    # Save cache
    with open(CACHE_FILE, "w") as f:
        json.dump(CACHE, f)
    print("💾 Cache updated.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_genres_ratings_async.py epg.xml epg_updated.xml")
        exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
