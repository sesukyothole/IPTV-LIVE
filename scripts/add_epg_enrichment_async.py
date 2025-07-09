import sys
import os
import asyncio
import aiohttp
import xml.etree.ElementTree as ET

TMDB_API_KEY = sys.argv[3] if len(sys.argv) > 3 else os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

HEADERS = {'Accept': 'application/json'}
GENRE_MAP = {}

async def fetch_json(session, url, params=None):
    async with session.get(url, params=params, headers=HEADERS) as response:
        return await response.json()

async def load_genres(session):
    for media_type in ["movie", "tv"]:
        url = f"{TMDB_BASE}/genre/{media_type}/list"
        params = {'api_key': TMDB_API_KEY}
        data = await fetch_json(session, url, params)
        for genre in data.get("genres", []):
            GENRE_MAP[genre["id"]] = genre["name"]

async def get_rating(session, media_type, tmdb_id):
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}/{'release_dates' if media_type == 'movie' else 'content_ratings'}"
    params = {'api_key': TMDB_API_KEY}
    data = await fetch_json(session, url, params)

    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "US":
            if media_type == "movie":
                for release in entry.get("release_dates", []):
                    cert = release.get("certification")
                    if cert:
                        return cert
            else:
                return entry.get("rating")
    return None

async def search_tmdb(session, title):
    for media_type in ["tv", "movie"]:
        url = f"{TMDB_BASE}/search/{media_type}"
        params = {'api_key': TMDB_API_KEY, 'query': title}
        result = await fetch_json(session, url, params)
        results = result.get("results", [])

        if not results:
            continue

        item = results[0]
        tmdb_id = item["id"]
        details = await fetch_json(session, f"{TMDB_BASE}/{media_type}/{tmdb_id}", {'api_key': TMDB_API_KEY})

        genres = [GENRE_MAP.get(gid) for gid in item.get("genre_ids", []) if gid in GENRE_MAP]
        poster = item.get("poster_path")
        description = details.get("overview")
        rating = await get_rating(session, media_type, tmdb_id)

        return {
            "poster": f"{TMDB_IMAGE_BASE}{poster}" if poster else None,
            "description": description,
            "genres": genres,
            "rating": rating
        }
    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel_id = programme.attrib.get("channel", "")

    if not (title_el is not None and title_el.text) or channel_id not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"🎬 Enriching: {title} (Channel: {channel_id})")

    data = await search_tmdb(session, title)
    if not data:
        print(f"❌ No TMDb match for {title}\n")
        return

    enriched = False

    if data["poster"]:
        ET.SubElement(programme, "icon", {"src": data["poster"]})
        print(f"✅ Poster added for {title}")
        enriched = True
    else:
        print(f"❌ Poster not found for {title}")

    if data["description"]:
        desc = ET.SubElement(programme, "desc")
        desc.text = data["description"]
        print(f"✅ Description added for {title}")
        enriched = True
    else:
        print(f"❌ Description not found for {title}")

    if data["genres"]:
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"✅ Genres added for {title}")
        enriched = True
    else:
        print(f"❌ Genres not found for {title}")

    if data["rating"]:
        rating = ET.SubElement(programme, "rating")
        value = ET.SubElement(rating, "value")
        value.text = data["rating"]
        print(f"✅ MPAA Rating added for {title}: {data['rating']}")
        enriched = True
    else:
        print(f"❌ Rating not found for {title}")

    print(f"{'✅' if enriched else '❌'} Enrichment {'completed' if enriched else 'failed'} for {title}\n")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await load_genres(session)
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n📄 EPG enrichment complete. Output written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 4 or not TMDB_API_KEY:
        print("Usage: python3 script.py epg.xml epg_updated.xml TMDB_API_KEY")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
