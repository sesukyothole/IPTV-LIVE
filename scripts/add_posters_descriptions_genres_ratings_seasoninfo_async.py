import aiohttp
import asyncio
import sys
import os
import xml.etree.ElementTree as ET

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w342"

HEADERS = {"Accept": "application/json"}

# 🎯 Target channel IDs (as strings)
TARGET_CHANNELS = {
    "403788", "493674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

ET.register_namespace('', "http://xmltv.org/xmltv")

async def fetch_json(session, url, params):
    async with session.get(url, params=params, headers=HEADERS) as response:
        return await response.json()

async def search_tmdb(session, title):
    result = {
        "poster": None,
        "description": None,
        "genres": [],
        "rating": "N/A",
        "season_episode": None
    }

    params = {"api_key": TMDB_API_KEY, "query": title}
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)

    tv_result = tv["results"][0] if tv["results"] else None
    movie_result = movie["results"][0] if movie["results"] else None

    show = tv_result or movie_result
    if not show:
        return result

    tmdb_id = show.get("id")

    # Poster
    if show.get("poster_path"):
        result["poster"] = TMDB_IMAGE_URL + show["poster_path"]

    # Description
    result["description"] = show.get("overview", "No description")

    # Genres (by genre_ids only — mapping could be improved if needed)
    result["genres"] = show.get("genre_ids", [])

    # Season/Episode (basic placeholder if title contains episode info)
    if "name" in show:
        result["season_episode"] = "S1E1"

    # Rating
    if tv_result:
        ratings = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", {"api_key": TMDB_API_KEY})
        us = next((r for r in ratings.get("results", []) if r.get("iso_3166_1") == "US"), None)
        if us:
            result["rating"] = us.get("rating", "N/A")
    elif movie_result:
        releases = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", {"api_key": TMDB_API_KEY})
        us = next((r for r in releases.get("results", []) if r.get("iso_3166_1") == "US"), None)
        if us:
            for release in us.get("release_dates", []):
                if release.get("certification"):
                    result["rating"] = release["certification"]
                    break

    return result

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel", "")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text
    print(f"🎬 Processing: {title} (Channel: {channel})")

    try:
        data = await search_tmdb(session, title)

        # Poster
        if data["poster"]:
            ET.SubElement(programme, "icon", {"src": data["poster"]})
            print(f"✅ Poster added for {title}")
        else:
            print(f"❌ Failed adding poster for {title}")

        # Description
        if data["description"]:
            ET.SubElement(programme, "desc").text = data["description"]
            print(f"✅ Description added for {title}")
        else:
            print(f"❌ Failed adding description for {title}")

        # Genres
        if data["genres"]:
            for genre in data["genres"]:
                ET.SubElement(programme, "category").text = str(genre)
            print(f"✅ Genres added for {title}")
        else:
            print(f"❌ No genres for {title}")

        # Rating
        ET.SubElement(ET.SubElement(programme, "rating"), "value").text = data["rating"]
        print(f"✅ Rating added for {title}: {data['rating']}")

        # Season/Episode
        if data["season_episode"]:
            ep = ET.SubElement(programme, "episode-num", {"system": "onscreen"})
            ep.text = data["season_episode"]
            print(f"✅ Season/Episode added for {title}: {data['season_episode']}")
        else:
            print(f"❌ No Season/Episode info for {title}")

        print(f"🏁 Completed all tasks for {title}\n")

    except Exception as e:
        print(f"❌ Exception for {title}: {str(e)}\n")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, prog) for prog in root.findall("programme")]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"📁 EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_descriptions_genres_ratings_seasoninfo_async.py input.xml output.xml")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
