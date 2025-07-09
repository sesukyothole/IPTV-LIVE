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
    try:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"❌ Network error: {e}")
    return {}

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}

    # Search TV shows first
    tv_data = await fetch_json(session, TMDB_SEARCH_TV, params)
    if tv_data.get("results"):
        show = tv_data["results"][0]
        return {
            "poster": TMDB_IMAGE_BASE + show["poster_path"] if show.get("poster_path") else None,
            "overview": show.get("overview", ""),
            "media_type": "TV Show"
        }

    # If not found, search Movies
    movie_data = await fetch_json(session, TMDB_SEARCH_MOVIE, params)
    if movie_data.get("results"):
        movie = movie_data["results"][0]
        return {
            "poster": TMDB_IMAGE_BASE + movie["poster_path"] if movie.get("poster_path") else None,
            "overview": movie.get("overview", ""),
            "media_type": "Movie"
        }

    return {"poster": None, "overview": "", "media_type": "Unknown"}

async def process_programme(session, programme, index, total):
    channel = programme.get("channel")
    title_el = programme.find("title")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip() if title_el.text else "Unknown Title"
    print(f"\n[{index}/{total}] 🔍 Processing: {title}")

    data = await search_tmdb(session, title)
    media_type = data["media_type"]

    success = True

    if data["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print(f"✅ Poster added for {media_type}: {title}")
    else:
        print(f"❌ Failed adding poster for {media_type}: {title}")
        success = False

    if data["overview"]:
        desc_el = ET.SubElement(programme, "desc")
        desc_el.text = data["overview"]
        print(f"📝 Description added for {media_type}: {title}")
    else:
        print(f"❌ Failed adding description for {media_type}: {title}")
        success = False

    if success:
        print(f"🎯 Add Poster and Description for {media_type}: {title} ✅ COMPLETED")
    else:
        print(f"💥 Add Poster and Description for {media_type}: {title} ❌ FAILED")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")
    total = len(programmes)

    async with aiohttp.ClientSession() as session:
        tasks = [
            process_programme(session, programme, i + 1, total)
            for i, programme in enumerate(programmes)
        ]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Final Output: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_genres_descriptions_async.py epg.xml epg_updated.xml")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
