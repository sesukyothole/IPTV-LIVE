import aiohttp
import asyncio
import xml.etree.ElementTree as ET
import sys
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # ✅ Get API key from environment
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {TMDB_API_KEY}"}
TARGET_CHANNELS = {
    "403788", "493674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

ET.register_namespace('', "http://www.w3.org/2001/XMLSchema-instance")


async def fetch_json(session, url, params=None):
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

    # First try as TV
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", {"query": title})
    if tv.get("results"):
        show = tv["results"][0]
        result["poster"] = TMDB_IMAGE_URL + show["poster_path"] if show.get("poster_path") else None
        result["description"] = show.get("overview")
        result["genres"] = await resolve_genres(session, show.get("genre_ids", []), "tv")
        result["rating"] = await get_rating(session, "tv", show["id"])
        result["season_episode"] = f"S{show.get('first_air_date', '')[:4]}E1" if show.get("first_air_date") else None
        return result

    # Fallback to Movie
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", {"query": title})
    if movie.get("results"):
        film = movie["results"][0]
        result["poster"] = TMDB_IMAGE_URL + film["poster_path"] if film.get("poster_path") else None
        result["description"] = film.get("overview")
        result["genres"] = await resolve_genres(session, film.get("genre_ids", []), "movie")
        result["rating"] = await get_rating(session, "movie", film["id"])
        return result

    return result


async def resolve_genres(session, genre_ids, media_type):
    genres = await fetch_json(session, f"{TMDB_BASE}/genre/{media_type}/list")
    id_to_name = {g["id"]: g["name"] for g in genres.get("genres", [])}
    return [id_to_name.get(gid, str(gid)) for gid in genre_ids]


async def get_rating(session, media_type, tmdb_id):
    data = await fetch_json(session, f"{TMDB_BASE}/{media_type}/{tmdb_id}/release_dates" if media_type == "movie" else f"{TMDB_BASE}/{media_type}/{tmdb_id}/content_ratings")
    results = data.get("results", [])
    for entry in results:
        if entry.get("iso_3166_1") == "US":
            if media_type == "movie":
                for rel in entry.get("release_dates", []):
                    if rel.get("certification"):
                        return rel["certification"]
            else:
                if entry.get("rating"):
                    return entry["rating"]
    return "N/A"


async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text
    print(f"🔍 Searching: {title}")
    try:
        data = await search_tmdb(session, title)

        if data["poster"]:
            ET.SubElement(programme, "icon", {"src": data["poster"]})
            print(f"🖼️ Poster added for {title}")
        else:
            print(f"❌ Poster not found for {title}")

        if data["description"]:
            desc = ET.SubElement(programme, "desc", {"lang": "en"})
            desc.text = data["description"]
            print(f"📝 Description added for {title}")
        else:
            print(f"❌ Description not found for {title}")

        if data["genres"]:
            for genre in data["genres"]:
                genre_el = ET.SubElement(programme, "category", {"lang": "en"})
                genre_el.text = genre
            print(f"🏷️ Genres added for {title}: {', '.join(data['genres'])}")
        else:
            print(f"❌ Genres not found for {title}")

        if data["rating"] and data["rating"] != "N/A":
            rating_el = ET.SubElement(programme, "rating", {"system": "MPAA"})
            value_el = ET.SubElement(rating_el, "value")
            value_el.text = data["rating"]
            print(f"🔞 Rating added for {title}: {data['rating']}")
        else:
            print(f"❌ No rating found for {title}")

        if data["season_episode"]:
            ep_el = ET.SubElement(programme, "episode-num", {"system": "onscreen"})
            ep_el.text = data["season_episode"]
            print(f"🎬 Season/Episode added for {title}: {data['season_episode']}")
        else:
            print(f"❌ No Season/Episode info for {title}")

        print(f"✅ Enrichment completed for {title}\n")
    except Exception as e:
        print(f"❌ Failed processing {title}: {e}")


async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, prog) for prog in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ EPG written to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or not TMDB_API_KEY:
        print("❗ TMDB_API_KEY is required as an environment variable.")
        sys.exit(1)

    input_xml = sys.argv[1]
    output_xml = sys.argv[2]
    asyncio.run(enrich_epg(input_xml, output_xml))
