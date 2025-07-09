import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import sys
import json

TMDB_API_KEY = os.environ['TMDB_API_KEY']
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

HEADERS = {'Accept': 'application/json'}

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

# Skip DeprecationWarnings
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

async def fetch_json(session, url, params):
    async with session.get(url, params=params, headers=HEADERS) as response:
        return await response.json()

async def search_tmdb(session, query):
    result = {
        "poster": None,
        "description": None,
        "genres": [],
        "rating": None,
        "season_episode": None
    }

    params = {"api_key": TMDB_API_KEY, "query": query, "language": "en-US", "include_adult": "false"}

    # Try TV first
    tv_data = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv_data.get("results"):
        tv = tv_data["results"][0]
        tmdb_id = tv.get("id")

        if tv.get("poster_path"):
            result["poster"] = TMDB_IMAGE_BASE + tv["poster_path"]

        result["description"] = tv.get("overview")
        result["season_episode"] = f"S{tv.get('first_air_date', 'N/A')[:4]}E01"

        # Get genres & rating
        full_tv = await fetch_json(session, f"{TMDB_BASE}/tv/{tmdb_id}", {"api_key": TMDB_API_KEY, "language": "en-US"})
        result["genres"] = [genre["name"] for genre in full_tv.get("genres", [])]
        result["rating"] = full_tv.get("content_ratings", {}).get("results", [])
        for r in result["rating"]:
            if r.get("iso_3166_1") == "US":
                result["rating"] = r.get("rating")
                break
        else:
            result["rating"] = "N/A"

        return result

    # Try Movie
    movie_data = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie_data.get("results"):
        movie = movie_data["results"][0]
        tmdb_id = movie.get("id")

        if movie.get("poster_path"):
            result["poster"] = TMDB_IMAGE_BASE + movie["poster_path"]

        result["description"] = movie.get("overview")

        # Get genres & rating
        full_movie = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}", {"api_key": TMDB_API_KEY, "language": "en-US"})
        result["genres"] = [genre["name"] for genre in full_movie.get("genres", [])]

        releases = await fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", {"api_key": TMDB_API_KEY})
        result["rating"] = "N/A"
        for rel in releases.get("results", []):
            if rel.get("iso_3166_1") == "US":
                for entry in rel.get("release_dates", []):
                    if entry.get("certification"):
                        result["rating"] = entry["certification"]
                        break

        return result

    return result

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text
    print(f"📺 Processing: {title}")

    try:
        data = await search_tmdb(session, title)

        # Add poster
        if data["poster"]:
            ET.SubElement(programme, "icon", src=data["poster"])
            print(f"🖼️ Poster added for: {title}")
        else:
            print(f"❌ Failed adding poster for: {title}")

        # Add description
        if data["description"]:
            desc_el = programme.find("desc")
            if desc_el is None:
                desc_el = ET.SubElement(programme, "desc")
            desc_el.text = data["description"]
            print(f"📝 Description added for: {title}")
        else:
            print(f"❌ Failed adding description for: {title}")

        # Add genres
        if data["genres"]:
            for genre in data["genres"]:
                cat = ET.SubElement(programme, "category")
                cat.text = genre
            print(f"🏷️ Genres added for: {title}")
        else:
            print(f"❌ No genres found for: {title}")

        # Add MPAA rating
        if data["rating"] and data["rating"] != "N/A":
            rating_el = ET.SubElement(programme, "rating")
            value = ET.SubElement(rating_el, "value")
            value.text = data["rating"]
            print(f"🔞 Rating added ({data['rating']}) for: {title}")
        else:
            print(f"❌ No rating found for: {title}")

        # Add Season/Episode (optional: mock as SYYYYE01 from air date)
        if data["season_episode"]:
            ep_el = ET.SubElement(programme, "episode-num", system="original-air-date")
            ep_el.text = data["season_episode"]
            print(f"🎬 Season/Episode added for: {title}")
        else:
            print(f"❌ No season/episode info for: {title}")

        print(f"✅ Done: {title}\n")

    except Exception as e:
        print(f"❗ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for programme in root.findall("programme"):
            tasks.append(process_programme(session, programme))
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 script.py input.xml output.xml")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
