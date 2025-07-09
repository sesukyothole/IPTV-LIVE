import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import sys
import json

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {TMDB_API_KEY}"}
TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

async def fetch_json(session, url, params=None):
    async with session.get(url, params=params) as response:
        if response.status == 200:
            return await response.json()
        return {}

async def search_tmdb(session, query):
    print(f"🔍 Searching TMDB for: {query}")
    params = {"query": query, "include_adult": False, "language": "en-US"}

    # First try TV shows
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv.get("results"):
        show = tv["results"][0]
        return {"type": "tv", "data": show}

    # Try movies
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie.get("results"):
        show = movie["results"][0]
        return {"type": "movie", "data": show}

    return {"type": None, "data": None}

async def get_details(session, tmdb_id, content_type):
    return await fetch_json(session, f"{TMDB_BASE}/{content_type}/{tmdb_id}", {"language": "en-US"})

async def process_programme(session, programme):
    channel = programme.get("channel")
    title_el = programme.find("title")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n🎬 Processing: {title}")

    tmdb_result = await search_tmdb(session, title)
    if not tmdb_result["data"]:
        print(f"❌ Not found on TMDB: {title}")
        return

    content_type = tmdb_result["type"]
    data = tmdb_result["data"]
    tmdb_id = data.get("id")

    if not tmdb_id:
        print(f"❌ No TMDB ID for: {title}")
        return

    details = await get_details(session, tmdb_id, content_type)

    # ✅ Add poster
    poster_path = details.get("poster_path")
    if poster_path:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", TMDB_IMAGE + poster_path)
        print(f"🖼️ Poster added for {title}")
    else:
        print(f"🚫 Failed adding poster for {title}")

    # ✅ Add description
    overview = details.get("overview")
    if overview:
        desc = ET.SubElement(programme, "desc")
        desc.text = overview
        print(f"📝 Description added for {title}")
    else:
        print(f"🚫 Failed adding description for {title}")

    # ✅ Add genres
    genres = details.get("genres", [])
    if genres:
        for g in genres:
            genre = ET.SubElement(programme, "category")
            genre.text = g["name"]
        print(f"🎭 Genres added: {', '.join(g['name'] for g in genres)}")
    else:
        print(f"🚫 No genres found for {title}")

    # ✅ Add MPAA Rating
    release = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{tmdb_id}/release_dates" if content_type == "movie" else f"{TMDB_BASE}/{content_type}/{tmdb_id}/content_ratings")
    rating = None

    if content_type == "movie":
        results = release.get("results", [])
        for r in results:
            if r.get("iso_3166_1") == "US":
                for rel in r.get("release_dates", []):
                    if "certification" in rel and rel["certification"]:
                        rating = rel["certification"]
                        break
    else:
        results = release.get("results", [])
        for r in results:
            if r.get("iso_3166_1") == "US" and r.get("rating"):
                rating = r["rating"]
                break

    if rating:
        rating_tag = ET.SubElement(programme, "rating")
        value_tag = ET.SubElement(rating_tag, "value")
        value_tag.text = f"MPAA:{rating}"
        print(f"🧒 MPAA Rating added: {rating}")
    else:
        print(f"🚫 No rating found for {title}")

    # ✅ Add Season/Episode Info
    season = data.get("first_air_date", "").split("-")[0] if content_type == "tv" else None
    episode_title = data.get("name" if content_type == "tv" else "title")

    if season and episode_title:
        episode_num = details.get("number_of_episodes", "1")
        ep_tag = ET.SubElement(programme, "episode-num")
        ep_tag.set("system", "xmltv_ns")
        ep_tag.text = f"{season}.0.{episode_num}"
        print(f"📺 Season/Episode Info added: S{season}E{episode_num}")
    else:
        print(f"🚫 No Season/Episode info for {title}")

    print(f"✅ Finished processing {title}")

async def enrich_epg(input_path, output_path):
    tree = ET.parse(input_path)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, prog) for prog in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print("\n✅ EPG written to", output_path)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 script.py epg.xml epg_updated.xml")
    else:
        asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
