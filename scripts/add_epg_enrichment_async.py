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

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_movie_rating(session, movie_id, api_key):
    details = await fetch_json(session, f"{TMDB_BASE}/movie/{movie_id}/release_dates", {"api_key": api_key})
    for result in details.get("results", []):
        if result.get("iso_3166_1") == "US":
            for release in result.get("release_dates", []):
                return release.get("certification", "").strip() or "Not Rated"
    return "Not Rated"

async def get_tv_rating(session, tv_id, api_key):
    details = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/content_ratings", {"api_key": api_key})
    for result in details.get("results", []):
        if result.get("iso_3166_1") == "US":
            return result.get("rating", "").strip() or "Not Rated"
    return "Not Rated"

async def search_tmdb(session, title, api_key):
    params = {"api_key": api_key, "query": title}
    result = {
        "poster": None,
        "description": None,
        "genres": [],
        "rating": "Not Rated"
    }

    tv_data = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    tv_results = tv_data.get("results", [])

    exact_tv = next((item for item in tv_results if item["name"].lower() == title.lower()), None)
    if exact_tv:
        show = exact_tv
        media_type = "tv"
    elif tv_results:
        show = tv_results[0]
        media_type = "tv"
    else:
        movie_data = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
        movie_results = movie_data.get("results", [])
        exact_movie = next((item for item in movie_results if item["title"].lower() == title.lower()), None)
        if exact_movie:
            show = exact_movie
            media_type = "movie"
        elif movie_results:
            show = movie_results[0]
            media_type = "movie"
        else:
            return result  # Not found

    result["poster"] = TMDB_IMAGE_BASE + (show.get("poster_path") or "")
    result["description"] = show.get("overview", "").strip()

    if media_type == "tv":
        full = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}", {"api_key": api_key})
        result["genres"] = [g["name"] for g in full.get("genres", [])]
        result["rating"] = await get_tv_rating(session, show["id"], api_key)
    else:
        full = await fetch_json(session, f"{TMDB_BASE}/movie/{show['id']}", {"api_key": api_key})
        result["genres"] = [g["name"] for g in full.get("genres", [])]
        result["rating"] = await get_movie_rating(session, show["id"], api_key)

    return result

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"🔎 Searching TMDb for: {title}")

    try:
        data = await search_tmdb(session, title, TMDB_API_KEY)
        success = False

        # Poster
        if data["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added for {title}")
            success = True
        else:
            print(f"❌ No poster for {title}")

        # Description
        if data["description"]:
            desc = programme.find("desc")
            if desc is None:
                desc = ET.SubElement(programme, "desc")
            desc.text = data["description"]
            print(f"📝 Description added for {title}")
            success = True
        else:
            print(f"❌ No description for {title}")

        # Genres
        if data["genres"]:
            for genre in data["genres"]:
                genre_el = ET.SubElement(programme, "category")
                genre_el.text = genre
            print(f"🏷️ Genres added for {title}: {', '.join(data['genres'])}")
            success = True
        else:
            print(f"❌ No genres for {title}")

        # MPAA Rating
        if data["rating"] and data["rating"] != "Not Rated":
            rating_el = ET.SubElement(programme, "rating")
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🎞️ MPAA Rating added for {title}: {data['rating']}")
            success = True
        else:
            print(f"⚠️ No MPAA Rating for {title}")

        if success:
            print(f"✅ Enrichment completed for {title}\n")
        else:
            print(f"⚠️ Enrichment failed for {title}\n")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}\n")

async def enrich_epg(input_path, output_path):
    tree = ET.parse(input_path)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"📁 EPG written to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py epg.xml epg_updated.xml TMDB_API_KEY")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
