import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import os
import sys

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMG_URL = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = [
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
]

HEADERS = {"accept": "application/json"}

async def fetch_json(session, url, params):
    async with session.get(url, params=params, headers=HEADERS) as resp:
        if resp.status == 200:
            return await resp.json()
        return {}

async def get_tmdb_data(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}

    # TV show first
    tv_res = await fetch_json(session, f"{TMDB_BASE_URL}/search/tv", params)
    if tv_res.get("results"):
        show = tv_res["results"][0]
        show_id = show["id"]

        details = await fetch_json(session, f"{TMDB_BASE_URL}/tv/{show_id}", {"api_key": TMDB_API_KEY})
        content_rating = await fetch_json(session, f"{TMDB_BASE_URL}/tv/{show_id}/content_ratings", {"api_key": TMDB_API_KEY})

        rating = "N/A"
        for entry in content_rating.get("results", []):
            if entry.get("iso_3166_1") == "US":
                rating = entry.get("rating", "N/A")

        return {
            "type": "tv",
            "poster": TMDB_IMG_URL + show["poster_path"] if show.get("poster_path") else None,
            "description": show.get("overview", ""),
            "genres": [g["name"] for g in details.get("genres", [])],
            "rating": rating,
            "season": show.get("first_air_date", "")[:4],
            "episode": "1"  # TMDB search API doesn't expose episode info
        }

    # Movie fallback
    movie_res = await fetch_json(session, f"{TMDB_BASE_URL}/search/movie", params)
    if movie_res.get("results"):
        movie = movie_res["results"][0]
        movie_id = movie["id"]

        details = await fetch_json(session, f"{TMDB_BASE_URL}/movie/{movie_id}", {"api_key": TMDB_API_KEY})
        releases = await fetch_json(session, f"{TMDB_BASE_URL}/movie/{movie_id}/release_dates", {"api_key": TMDB_API_KEY})

        rating = "N/A"
        for result in releases.get("results", []):
            if result["iso_3166_1"] == "US":
                for release in result.get("release_dates", []):
                    if release.get("certification"):
                        rating = release["certification"]
                        break

        return {
            "type": "movie",
            "poster": TMDB_IMG_URL + movie["poster_path"] if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "genres": [g["name"] for g in details.get("genres", [])],
            "rating": rating,
            "season": None,
            "episode": None
        }

    return {
        "type": "unknown",
        "poster": None,
        "description": "",
        "genres": [],
        "rating": "N/A",
        "season": None,
        "episode": None
    }

async def process_programme(session, programme, index, total):
    channel = programme.get("channel")
    title_el = programme.find("title")

    if not title_el or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n[{index}/{total}] 🎬 Processing: {title}")

    data = await get_tmdb_data(session, title)

    poster_success = False
    desc_success = False

    # Poster
    if data["poster"]:
        ET.SubElement(programme, "icon", {"src": data["poster"]})
        print(f"🖼️ Poster added for '{title}'")
        poster_success = True
    else:
        print(f"❌ Failed adding poster for '{title}'")

    # Description
    if data["description"]:
        desc_el = ET.SubElement(programme, "desc")
        desc_el.text = data["description"]
        print(f"📝 Description added for '{title}'")
        desc_success = True
    else:
        print(f"❌ Failed adding description for '{title}'")

    # Genres
    if data["genres"]:
        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🏷️ Genres added for '{title}': {', '.join(data['genres'])}")
    else:
        print(f"❌ No genres found for '{title}'")

    # Rating
    if data["rating"] and data["rating"] != "N/A":
        rating_el = ET.SubElement(programme, "rating", {"system": "MPAA"})
        val_el = ET.SubElement(rating_el, "value")
        val_el.text = data["rating"]
        print(f"🔞 MPAA Rating added for '{title}': {data['rating']}")
    else:
        print(f"❌ No MPAA rating found for '{title}'")

    # Season & Episode
    if data["season"] and data["episode"]:
        ep = ET.SubElement(programme, "episode-num", {"system": "onscreen"})
        ep.text = f"S1E{data['episode']}"
        print(f"📺 Season/Episode added for '{title}': S1E{data['episode']}")
    else:
        print(f"⚠️ No episode info found for '{title}'")

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
        tasks = [
            process_programme(session, programme, idx + 1, total)
            for idx, programme in enumerate(programmes)
        ]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n📁 ✅ EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_posters_descriptions_genres_ratings_seasoninfo_async.py input.xml output.xml")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
