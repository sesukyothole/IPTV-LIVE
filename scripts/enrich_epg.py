import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import sys
import os
import logging
from datetime import datetime
from genre_colors import get_color_for_genre

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# TMDB Setup
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not TMDB_API_KEY:
    log.error("❌ TMDB_API_KEY is required.")
    sys.exit(1)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"  # Bigger size than w500

TARGET_CHANNELS = {
    "403788", "403674", "403837",
    "403794", "403620", "403772",
    "403655", "403847", "403576", 
    "403576", "403823", "403928",
    "403522", "403926", "403650",
    "403933", "403824", "403578",
    "403563", "403838", "403486",
    "403815", "403717", "403518",  
    "403786", "403726", "403529",  
    "403730", "403520", "403455",
    "403581", "403646", "440244",
    "403512", "403461", "403829"
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
    "The Really Loud House": {"type": "tv", "id": 211779},
    "Lilo & Stitch": {"type": "tv", "id": 2355},
    "Disney's Kim Possible Movie: So the Drama": {"type": "movie", "id": 20771},
    "My Cousin Rachel": {"type": "movie", "id": 413998},
    "Tuesday": {"type": "movie", "id": 831395},
    "The Huntsman: Winter's War": {"type": "movie", "id": 290595},
    "Blue Beetle": {"type": "movie", "id": 565770},
    "Unknown": {"type": "movie", "id": 48138}
}

TMDB_GENRES = {
    16: "Animation", 35: "Comedy", 10751: "Family", 10762: "Kids", 18: "Drama",
    28: "Action", 10759: "Adventure", 12: "Adventure", 14: "Fantasy", 27: "Horror",
    10402: "Music", 9648: "Mystery", 878: "Sci-Fi", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics"
}

# TMDb API Helpers

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        return await resp.json()

async def get_details(session, content_type, content_id):
    return await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}", {"api_key": TMDB_API_KEY})

async def get_credits(session, content_type, content_id):
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/credits", {"api_key": TMDB_API_KEY})
    cast = [c["name"] for c in data.get("cast", [])]
    directors = [c["name"] for c in data.get("crew", []) if c.get("job") == "Director"]
    return cast, directors[0] if directors else None

async def get_rating(session, content_type, content_id):
    endpoint = "release_dates" if content_type == "movie" else "content_ratings"
    data = await fetch_json(session, f"{TMDB_BASE}/{content_type}/{content_id}/{endpoint}", {"api_key": TMDB_API_KEY})
    for r in data.get("results", []):
        if r.get("iso_3166_1") == "US":
            if content_type == "movie":
                for rel in r.get("release_dates", []):
                    if rel.get("certification"):
                        return rel.get("certification")
            else:
                return r.get("rating")
    return "Not Rated"

async def get_episode_info(session, tv_id, airdate_str):
    try:
        airdate = datetime.strptime(airdate_str, "%Y%m%d").date()
    except:
        return None, None, None, None

    for season in range(1, 100):
        data = await fetch_json(session, f"{TMDB_BASE}/tv/{tv_id}/season/{season}", {"api_key": TMDB_API_KEY})
        for ep in data.get("episodes", []):
            if ep.get("air_date") == airdate.isoformat():
                return season, ep["episode_number"], ep["name"], ep["overview"]
        if not data.get("episodes"):
            break
    return None, None, None, None

# Main Enrichment Logic

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")
    if title_el is None or not channel or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    log.info(f"📺 Processing: {title}")

    start = programme.get("start")
    airdate_str = start[:8] if start else None

    try:
        if title in MANUAL_ID_OVERRIDES:
            ovr = MANUAL_ID_OVERRIDES[title]
            details = await get_details(session, ovr["type"], ovr["id"])
            rating = await get_rating(session, ovr["type"], ovr["id"])
            cast, director = await get_credits(session, ovr["type"], ovr["id"])
            first_air_date_raw = details.get("first_air_date") or details.get("release_date")
            data = {
                "title": details.get("name") or details.get("title"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [TMDB_GENRES.get(g["id"]) for g in details.get("genres", []) if TMDB_GENRES.get(g["id"])],
                "year": first_air_date_raw[:4] if first_air_date_raw else "",
                "first_air_date": datetime.strptime(first_air_date_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if first_air_date_raw else "",
                "rating": rating,
                "cast": cast,
                "director": director,
                "id": ovr["id"],
                "type": ovr["type"]
            }
        else:
            search = await fetch_json(session, f"{TMDB_BASE}/search/multi", {
                "api_key": TMDB_API_KEY, "query": title
            })
            result = next((r for r in search.get("results", []) if r["media_type"] in ("tv", "movie")), None)
            if not result:
                log.warning(f"❌ No match found for: {title}")
                return
            content_type = result["media_type"]
            content_id = result["id"]
            details = await get_details(session, content_type, content_id)
            rating = await get_rating(session, content_type, content_id)
            cast, director = await get_credits(session, content_type, content_id)
            first_air_date_raw = details.get("first_air_date") or details.get("release_date")
            data = {
                "title": details.get("name") or details.get("title"),
                "poster": TMDB_IMAGE_BASE + (details.get("poster_path") or ""),
                "description": details.get("overview", "").strip(),
                "genres": [TMDB_GENRES.get(g["id"]) for g in details.get("genres", []) if TMDB_GENRES.get(g["id"])],
                "year": first_air_date_raw[:4] if first_air_date_raw else "",
                "first_air_date": datetime.strptime(first_air_date_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if first_air_date_raw else "",
                "rating": rating,
                "cast": cast,
                "director": director,
                "id": content_id,
                "type": content_type
            }

        if data["poster"]:
            ET.SubElement(programme, "icon", {"src": data["poster"]})

        desc_el = programme.find("desc") or ET.SubElement(programme, "desc")
        desc_text = data["description"]

        if data["type"] == "tv" and airdate_str:
            season, episode, ep_title, ep_overview = await get_episode_info(session, data["id"], airdate_str)
            if season and episode:
                ET.SubElement(programme, "episode-num", {"system": "xmltv_ns"}).text = f"{season-1}.{episode-1}."
                ET.SubElement(programme, "episode-num", {"system": "onscreen"}).text = f"S{season}E{episode}"
            if ep_title:
                ET.SubElement(programme, "sub-title").text = ep_title
            if ep_overview:
                desc_text = ep_overview

        if data["director"] or data["cast"]:
            desc_text += "\n\n"
            if data["director"]:
                desc_text += f"🎬 Director: {data['director']}\n"
            if data["cast"]:
                desc_text += f"🎭 Cast: {', '.join(data['cast'][:6])}"

        desc_el.text = desc_text

        for g in data["genres"]:
            cat_el = ET.SubElement(programme, "category")
            cat_el.text = g
            cat_el.set("color", get_color_for_genre(g))

        if data["first_air_date"]:
            date_el = programme.find("date") or ET.SubElement(programme, "date")
            date_el.text = data["first_air_date"]

        if data["rating"] and data["rating"] not in ("", "Not Rated"):
            rating_el = ET.SubElement(programme, "rating")
            ET.SubElement(rating_el, "value").text = data["rating"]



        if data["cast"] or data["director"]:
            credits = programme.find("credits") or ET.SubElement(programme, "credits")
            if data["director"]:
                ET.SubElement(credits, "director").text = data["director"]
            for actor in data["cast"][:6]:
                ET.SubElement(credits, "actor").text = actor

        log.info(f"✅ Enriched: {title}")

    except Exception as e:
        log.error(f"❌ Error processing {title}: {e}")

# Runner

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[
            asyncio.create_task(process_programme(session, p)) for p in programmes
            if p.get("channel") in TARGET_CHANNELS
        ])

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    log.info(f"🎉 Enriched EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        log.error("Usage: python3 enrich_epg.py epg.xml enriched_epg.xml [TMDB_API_KEY]")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
