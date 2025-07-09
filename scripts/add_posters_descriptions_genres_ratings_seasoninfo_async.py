import sys
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import re
import os

TMDB_API_KEY = os.environ.get("TMDB_API_KEY") or (sys.argv[3] if len(sys.argv) > 3 else None)
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

HEADERS = {"Accept": "application/json"}
GENRE_CACHE = {}

async def fetch(session, url, params=None):
    async with session.get(url, params=params, headers=HEADERS) as res:
        return await res.json()

async def get_genres(session, media_type):
    if media_type in GENRE_CACHE:
        return GENRE_CACHE[media_type]
    url = f"{TMDB_BASE}/genre/{media_type}/list"
    genres = await fetch(session, url, {"api_key": TMDB_API_KEY})
    GENRE_CACHE[media_type] = {g["id"]: g["name"] for g in genres.get("genres", [])}
    return GENRE_CACHE[media_type]

async def get_rating(session, media_type, tmdb_id):
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}/{'content_ratings' if media_type == 'tv' else 'release_dates'}"
    data = await fetch(session, url, {"api_key": TMDB_API_KEY})
    ratings = data.get("results", [])

    for entry in ratings:
        if entry.get("iso_3166_1") == "US":
            if media_type == "tv":
                return entry.get("rating")
            elif media_type == "movie":
                for r in entry.get("release_dates", []):
                    if r.get("certification"):
                        return r["certification"]
    return None

async def search_tmdb(session, title):
    for media_type in ["movie", "tv"]:
        search_url = f"{TMDB_BASE}/search/{media_type}"
        params = {"api_key": TMDB_API_KEY, "query": title}
        results = await fetch(session, search_url, params)

        if results.get("results"):
            show = results["results"][0]
            tmdb_id = show["id"]
            details_url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
            details = await fetch(session, details_url, {"api_key": TMDB_API_KEY})
            genres = await get_genres(session, media_type)
            rating = await get_rating(session, media_type, tmdb_id)

            genre_names = [genres.get(gid) for gid in show.get("genre_ids", []) if genres.get(gid)]
            poster = show.get("poster_path")
            season_info = None

            if media_type == "tv" and "name" in show:
                match = re.search(r"[Ss](\d+)[Ee](\d+)", title)
                if match:
                    season_info = f"S{int(match.group(1)):02d}E{int(match.group(2)):02d}"

            return {
                "title": title,
                "media_type": media_type,
                "poster": TMDB_IMAGE + poster if poster else None,
                "description": details.get("overview"),
                "genres": genre_names,
                "rating": rating,
                "season_info": season_info
            }
    return None

async def enrich_programme(session, programme):
    title_el = programme.find("title")
    if title_el is None or not title_el.text:
        return

    title = title_el.text.strip()
    print(f"🔍 Searching for: {title}")

    result = await search_tmdb(session, title)
    if not result:
        print(f"❌ No result found for {title}")
        return

    added = False

    # Poster
    if result["poster"]:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", result["poster"])
        print(f"🖼️ Poster added for {title}")
        added = True
    else:
        print(f"❌ Poster not found for {title}")

    # Description
    if result["description"]:
        desc = ET.SubElement(programme, "desc")
        desc.text = result["description"]
        print(f"📄 Description added for {title}")
        added = True
    else:
        print(f"❌ Description not found for {title}")

    # Genres
    if result["genres"]:
        for genre in result["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🏷️ Genres added for {title}: {', '.join(result['genres'])}")
        added = True
    else:
        print(f"❌ Genres not found for {title}")

    # Rating
    if result["rating"]:
        rating_el = ET.SubElement(programme, "rating")
        rating_val = ET.SubElement(rating_el, "value")
        rating_val.text = result["rating"]
        print(f"🎯 Rating added for {title}: {result['rating']}")
        added = True
    else:
        print(f"❌ Rating not found for {title}")

    # Season/Episode
    if result["season_info"]:
        episode_el = ET.SubElement(programme, "episode-num")
        episode_el.set("system", "onscreen")
        episode_el.text = result["season_info"]
        print(f"📺 Episode info added for {title}: {result['season_info']}")
        added = True
    else:
        print(f"❌ No Season/Episode info for {title}")

    if added:
        print(f"✅ Enrichment completed for {title}\n")
    else:
        print(f"⚠️ Enrichment failed for {title}\n")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [enrich_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 script.py input.xml output.xml [TMDB_API_KEY]")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
