import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import sys

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        if resp.status == 200:
            return await resp.json()
        return {}

async def search_tmdb(session, title):
    # First try TV
    params = {"api_key": TMDB_API_KEY, "query": title}
    data = await fetch_json(session, TMDB_SEARCH_TV, params)
    if data.get("results"):
        show = data["results"][0]
        return {
            "poster": TMDB_IMAGE_BASE + show["poster_path"] if show.get("poster_path") else None,
            "genres": [g for g in show.get("genre_ids", [])],  # IDs, not names, fallback logic
            "overview": show.get("overview", "")
        }

    # Then try Movie
    data = await fetch_json(session, TMDB_SEARCH_MOVIE, params)
    if data.get("results"):
        movie = data["results"][0]
        return {
            "poster": TMDB_IMAGE_BASE + movie["poster_path"] if movie.get("poster_path") else None,
            "genres": [g for g in movie.get("genre_ids", [])],  # IDs, not names, fallback logic
            "overview": movie.get("overview", "")
        }

    return {"poster": None, "genres": [], "overview": ""}

async def process_programme(session, programme, index, total):
    channel = programme.get("channel")
    title_el = programme.find("title")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text
    print(f"[{index}/{total}] 🎬 Processing: {title}")

    data = await search_tmdb(session, title)

    # Poster
    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print("✅ Poster added")
    else:
        print("❌ No poster found")

    # Overview (description)
    if data["overview"]:
        desc_el = ET.SubElement(programme, "desc")
        desc_el.text = data["overview"]
        print("📝 Description added")
    else:
        print("❌ No description found")

    # Genre
    if data["genres"]:
        for genre_name in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = str(genre_name)
        print("🏷️ Genres added")
    else:
        print("❌ No genres found")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")
    total = len(programmes)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, programme in enumerate(programmes, 1):
            tasks.append(process_programme(session, programme, i, total))
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_genres_descriptions_async.py input.xml output.xml")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
