import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os
from datetime import datetime

TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY is required.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "403847", "403772", "403576", "403926",
    "403461"
}

MANUAL_ID_OVERRIDES = {
    "Jessie": {"type": "tv", "id": 38974},
    "Big City Greens": {"type": "tv", "id": 80587},
    "Kiff": {"type": "tv", "id": 127706},
    "Zombies": {"type": "movie", "id": 483980},
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id": 585},
    "The Incredibles": {"type": "movie", "id": 9806},
    "SpongeBob SquarePants": {"type": "tv", "id": 387},
    "Peppa Pig": {"type": "tv", "id": 12225},
    "PAW Patrol": {"type": "tv", "id": 57532},
    "Rubble & Crew": {"type": "tv", "id": 214875},
    "Gabby's Dollhouse": {"type": "tv", "id": 111474},
    "black-ish": {"type": "tv", "id": 61381},
    "Phineas and Ferb": {"type": "tv", "id": 1877},
    "Win or Lose": {"type": "tv", "id": 114500},
    "Friends": {"type": "tv", "id": 1668},
    "Primos": {"type": "tv", "id": 204139},
    "DuckTales": {"type": "tv", "id": 72350},
    "Mulan": {"type": "movie", "id": 337401},
    "Moana": {"type": "movie", "id": 277834},
    "Modern Family": {"type": "tv", "id": 1421},
    "Henry Danger": {"type": "tv", "id": 61852},
    "The Really Loud House": {"type": "tv", "id": 211779}
}

TMDB_GENRES = {
    16: "Animation", 35: "Comedy", 10751: "Family", 10762: "Kids", 18: "Drama",
    28: "Action", 10759: "Adventure", 12: "Adventure", 14: "Fantasy", 27: "Horror",
    10402: "Music", 9648: "Mystery", 878: "Sci-Fi", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics"
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def get_details(session, content_type, content_id):
    return await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}", {"api_key": TMDB_API_KEY})

async def get_credits(session, content_type, content_id):
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/credits", {"api_key": TMDB_API_KEY})
    cast = [member["name"] for member in data.get("cast", [])]
    directors = [crew["name"] for crew in data.get("crew", []) if crew.get("job") == "Director"]
    return cast, directors[0] if directors else None

async def get_rating(session, content_type, content_id):
    endpoint = "release_dates" if content_type == "movie" else "content_ratings"
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/{endpoint}", {"api_key": TMDB_API_KEY})
    results = data.get("results", [])
    for entry in results:
        if entry.get("iso_3166_1") == "US":
            if content_type == "movie":
                for rel in entry.get("release_dates", []):
                    cert = rel.get("certification")
                    if cert:
                        return cert
            else:
                return entry.get("rating")
    return "Not Rated"

async def get_landscape_backdrop(session, content_type, content_id):
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/images", {
        "api_key": TMDB_API_KEY,
        "include_image_language": "en,null"
    })
    backdrops = data.get("backdrops", [])
    if backdrops:
        return "https://image.tmdb.org/t/p/w780" + backdrops[0]["file_path"]
    return None

async def get_episode_info(session, tv_id, airdate_str):
    try:
        airdate = datetime.strptime(airdate_str, "%Y%m%d").date()
    except:
        return None, None, None

    for season_num in range(1, 100):
        season_data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/season/{season_num}", {
            "api_key": TMDB_API_KEY
        })
        episodes = season_data.get("episodes", [])
        for ep in episodes:
            if ep.get("air_date"):
                ep_air = datetime.strptime(ep["air_date"], "%Y-%m-%d").date()
                if ep_air == airdate:
                    return season_num, ep.get("episode_number"), ep.get("name")
        if not episodes:
            break
    return None, None, None

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}
    movie_data = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie_data.get("results"):
        result = movie_data["results"][0]
        rating = await get_rating(session, "movie", result["id"])
        cast, director = await get_credits(session, "movie", result["id"])
        return {
            "title": result.get("title"),
            "poster": TMDB_IMAGE_BASE + (result.get("poster_path") or ""),
            "description": result.get("overview", "").strip(),
            "genres": [TMDB_GENRES.get(gid) for gid in result.get("genre_ids", []) if TMDB_GENRES.get(gid)],
            "year": result.get("release_date", "")[:4],
            "rating": rating,
            "cast": cast,
            "director": director,
            "id": result["id"],
            "type": "movie"
        }

    tv_data = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv_data.get("results"):
        result = tv_data["results"][0]
        rating = await get_rating(session, "tv", result["id"])
        cast, director = await get_credits(session, "tv", result["id"])
        return {
            "title": result.get("name"),
            "poster": TMDB_IMAGE_BASE + (result.get("poster_path") or ""),
            "description": result.get("overview", "").strip(),
            "genres": [TMDB_GENRES.get(gid) for gid in result.get("genre_ids", []) if TMDB_GENRES.get(gid)],
            "year": result.get("first_air_date", "")[:4],
            "rating": rating,
            "cast": cast,
            "director": director,
            "id": result["id"],
            "type": "tv"
        }

    return None

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")
    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"\n📺 Processing: {title}")

    start = programme.get("start")
    airdate_str = start[:8] if start else None

    try:
        if title in MANUAL_ID_OVERRIDES:
            override = MANUAL_ID_OVERRIDES[title]
            details = await get_details(session, override["type"], override["id"])
            rating = await get_rating(session, override["type"], override["id"])
            cast, director = await get_credits(session, override["type"], override["id"])
            data = {
                "title": details.get("name") or details.get("title"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [TMDB_GENRES.get(gid) for gid in [g["id"] for g in details.get("genres", [])] if TMDB_GENRES.get(gid)],
                "year": (details.get("first_air_date") or details.get("release_date") or "")[:4],
                "rating": rating,
                "cast": cast,
                "director": director,
                "id": override["id"],
                "type": override["type"]
            }
        else:
            data = await search_tmdb(session, title)

        if not data:
            print(f"❌ No match found for: {title}")
            return

        # Portrait
        if data["poster"]:
            icon = programme.find("icon")
            if icon is None:
                icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])

        # Landscape
        backdrop = await get_landscape_backdrop(session, data["type"], data["id"])
        if backdrop:
            ET.SubElement(programme, "icon", {"src": backdrop, "aspect": "landscape"})

        # Description with cast/director
        desc = programme.find("desc")
        if desc is None:
            desc = ET.SubElement(programme, "desc")
        desc_text = data["description"]
        if data["director"] or data["cast"]:
            desc_text += "\n\n"
            if data["director"]:
                desc_text += f"🎬 Director: {data['director']}\n"
            if data["cast"]:
                desc_text += f"🎭 Cast: {', '.join(data['cast'])}"
        desc.text = desc_text

        # Genres
        for g in data["genres"]:
            ET.SubElement(programme, "category").text = g

        # Year
        if data["year"]:
            date_el = programme.find("date")
            if date_el is None:
                date_el = ET.SubElement(programme, "date")
            date_el.text = data["year"]

        # Rating
        if data["rating"]:
            rating_el = ET.SubElement(programme, "rating")
            ET.SubElement(rating_el, "value").text = data["rating"]

        # Credits
        if data["cast"] or data["director"]:
            credits_el = programme.find("credits")
            if credits_el is None:
                credits_el = ET.SubElement(programme, "credits")
            for actor in data["cast"]:
                ET.SubElement(credits_el, "actor").text = actor
            if data["director"]:
                ET.SubElement(credits_el, "director").text = data["director"]

        # Episode info
        if data["type"] == "tv" and airdate_str:
            season, episode, ep_title = await get_episode_info(session, data["id"], airdate_str)
            if season and episode:
                ET.SubElement(programme, "episode-num", {"system": "xmltv_ns"}).text = f"{season-1}.{episode-1}."
                ET.SubElement(programme, "episode-num", {"system": "onscreen"}).text = f"S{season}E{episode}"
            if ep_title:
                ET.SubElement(programme, "sub-title").text = ep_title

        print(f"✅ Done: {title}")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Enriched EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 enrich_epg_async.py guide.xml epg_updated.xml [TMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))