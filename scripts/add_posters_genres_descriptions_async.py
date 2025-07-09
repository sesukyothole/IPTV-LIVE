import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import sys

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

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
    params = {"api_key": TMDB_API_KEY, "query": title}

    # Try TV show first
    tv_data = await fetch_json(session, TMDB_SEARCH_TV, params)
    if tv_data.get("results"):
        show = tv_data["results"][0]
        return {
            "type": "tv",
            "poster": TMDB_IMAGE_URL + show["poster_path"] if show.get("poster_path") else None,
            "description": show.get("overview", "")
        }

    # Try movie
    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE, params)
    if movie_data.get("results"):
        movie = movie_data["results"][0]
        return {
            "type": "movie",
            "poster": TMDB_IMAGE_URL + movie["poster_path"] if movie.get("poster_path") else None,
            "description": movie.get("overview", "")
        }

    return {
        "type": "unknown",
        "poster": None,
        "description": ""
    }

async def process_programme(session, programme, index, total):
    channel = programme.get("channel")
    title_el = programme.find("title")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n[{index}/{total}] 🎬 Processing: {title}")

    data = await search_tmdb(session, title)

    poster_success = False
    desc_success = False

    # Add portrait poster (Kodi-compatible)
    if data["poster"]:
        icon_el = ET.SubElement(programme, "icon")
        icon_el.set("src", data["poster"])
        print(f"🖼️ Poster added for '{title}'")
        poster_success = True
    else:
        print(f"❌ Failed adding poster for '{title}'")

    # Add description
    if data["description"]:
        desc_el = ET.SubElement(programme, "desc")
        desc_el.text = data["description"]
        print(f"📝 Description added for '{title}'")
        desc_success = True
    else:
        print(f"❌ Failed adding description for '{title}'")

    # Final log
    if poster_success and desc_success:
        print(f"✅ Add Poster and Description for '{title}' completed")
    else:
        print(f"⚠️ Add Poster and Description for '{title}' failed")

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
    print(f"\n📁 ✅ EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_descriptions_async.py input.xml output.xml")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
