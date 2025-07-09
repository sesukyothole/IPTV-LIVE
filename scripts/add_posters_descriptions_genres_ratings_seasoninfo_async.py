import sys
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os

TMDB_API_KEY = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

HEADERS = {'Accept': 'application/json'}

GENRE_MAP = {}  # Global genre name map for caching


async def fetch_json(session, url, params=None):
    async with session.get(url, params=params, headers=HEADERS) as response:
        return await response.json()


async def get_genres(session, media_type):
    global GENRE_MAP
    url = f"{TMDB_BASE}/genre/{media_type}/list"
    params = {'api_key': TMDB_API_KEY}
    data = await fetch_json(session, url, params)
    for genre in data.get("genres", []):
        GENRE_MAP[genre["id"]] = genre["name"]


async def get_rating(session, media_type, tmdb_id):
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}/{'release_dates' if media_type == 'movie' else 'content_ratings'}"
    params = {'api_key': TMDB_API_KEY}
    data = await fetch_json(session, url, params)

    results = data.get("results", [])
    for entry in results:
        if (entry.get("iso_3166_1") == "US") and "release_dates" in entry:
            for rd in entry["release_dates"]:
                if "certification" in rd and rd["certification"]:
                    return rd["certification"]
        elif (entry.get("iso_3166_1") == "US") and "rating" in entry:
            return entry["rating"]
    return None


async def search_tmdb(session, title):
    for media_type in ["tv", "movie"]:
        search_url = f"{TMDB_BASE}/search/{media_type}"
        params = {'api_key': TMDB_API_KEY, 'query': title}
        results = await fetch_json(session, search_url, params)
        results = results.get("results", [])

        if results:
            item = results[0]
            tmdb_id = item["id"]
            details_url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
            details = await fetch_json(session, details_url, {'api_key': TMDB_API_KEY})

            genres = [GENRE_MAP.get(genre["id"], "") for genre in item.get("genre_ids", [])]
            genres = list(filter(None, genres))

            rating = await get_rating(session, media_type, tmdb_id)
            description = details.get("overview")
            poster_path = item.get("poster_path")
            poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None

            return {
                "poster": poster_url,
                "description": description,
                "genres": genres,
                "rating": rating,
                "media_type": media_type
            }

    return None


async def process_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        return

    title = title_el.text.strip()
    print(f"🔍 Searching TMDb for: {title}")
    data = await search_tmdb(session, title)

    if not data:
        print(f"❌ No data found for {title}")
        return

    success = False

    if data.get("poster"):
        icon = ET.SubElement(programme, "icon")
        icon.set("src", data["poster"])
        print(f"✅ Poster added for {title}")
        success = True
    else:
        print(f"❌ Poster not found for {title}")

    if data.get("description"):
        desc = ET.SubElement(programme, "desc")
        desc.text = data["description"]
        print(f"✅ Description added for {title}")
        success = True
    else:
        print(f"❌ Description not found for {title}")

    if data.get("genres"):
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"✅ Genres added for {title}")
        success = True
    else:
        print(f"❌ Genres not found for {title}")

    if data.get("rating"):
        rating_el = ET.SubElement(programme, "rating")
        value = ET.SubElement(rating_el, "value")
        value.text = data["rating"]
        print(f"✅ Rating added for {title}: {data['rating']}")
        success = True
    else:
        print(f"❌ Rating not found for {title}")

    if success:
        print(f"✅ Enrichment completed for {title}\n")
    else:
        print(f"❌ Enrichment failed for {title}\n")


async def enrich_epg(input_file, output_file):
    ET.register_namespace("", "http://xmltv.org/xmltv")
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall(".//programme")

    async with aiohttp.ClientSession() as session:
        await get_genres(session, "movie")
        await get_genres(session, "tv")

        tasks = [process_programme(session, programme) for programme in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ EPG written to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or not TMDB_API_KEY:
        print("Usage: python3 add_posters_descriptions_genres_ratings_async.py <input.xml> <output.xml> <TMDB_API_KEY>")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
