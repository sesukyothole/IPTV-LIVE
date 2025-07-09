import sys
import asyncio
import aiohttp
import xml.etree.ElementTree as ET

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as resp:
        return await resp.json()

async def get_movie_rating(session, movie_id, api_key):
    url = f"{TMDB_BASE}/movie/{movie_id}/release_dates"
    data = await fetch_json(session, url, {"api_key": api_key})
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "US":
            for release in entry.get("release_dates", []):
                cert = release.get("certification", "").strip()
                if cert:
                    return cert
    return None

async def get_tv_rating(session, tv_id, api_key):
    url = f"{TMDB_BASE}/tv/{tv_id}/content_ratings"
    data = await fetch_json(session, url, {"api_key": api_key})
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "US":
            rating = entry.get("rating", "").strip()
            if rating:
                return rating
    return None

async def search_tmdb(session, title, api_key):
    params = {"api_key": api_key, "query": title}
    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)

    result = {
        "poster": None,
        "description": None,
        "genres": [],
        "rating": None
    }

    show = None
    media_type = None

    if movie.get("results"):
        show = movie["results"][0]
        media_type = "movie"
    elif tv.get("results"):
        show = tv["results"][0]
        media_type = "tv"

    if not show:
        return result

    result["poster"] = TMDB_IMAGE_BASE + (show.get("poster_path") or "")
    result["description"] = show.get("overview", "").strip()

    # Get genres and rating
    if media_type == "movie":
        full = await fetch_json(session, f"{TMDB_BASE}/movie/{show['id']}", {"api_key": api_key})
        result["genres"] = [g["name"] for g in full.get("genres", [])]
        result["rating"] = await get_movie_rating(session, show["id"], api_key)
    else:
        full = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}", {"api_key": api_key})
        result["genres"] = [g["name"] for g in full.get("genres", [])]
        result["rating"] = await get_tv_rating(session, show["id"], api_key)

    return result

async def process_programme(session, programme, api_key):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"🎬 Processing: {title} ({channel})")

    data = await search_tmdb(session, title, api_key)

    # Poster
    if data["poster"]:
        icon_el = ET.SubElement(programme, "icon")
        icon_el.set("src", data["poster"])
        print(f"🖼️ Poster added for {title}")
    else:
        print(f"❌ No poster found for {title}")

    # Description
    desc_el = programme.find("desc")
    if desc_el is None:
        desc_el = ET.SubElement(programme, "desc")
    desc_el.text = data["description"] or "No description available"
    print(f"📝 Description added for {title}")

    # Genres
    for genre in data["genres"]:
        genre_el = ET.SubElement(programme, "category")
        genre_el.text = genre
    print(f"🏷️ Genres added for {title}: {', '.join(data['genres']) or 'None'}")

    # Clear existing ratings
    for rating_tag in programme.findall("rating"):
        programme.remove(rating_tag)

    # Add MPAA Rating (Estuary MOD V2 compatible)
    if data["rating"]:
        rating_el = ET.SubElement(programme, "rating")
        rating_el.set("system", "MPAA")
        value_el = ET.SubElement(rating_el, "value")
        value_el.text = data["rating"]
        print(f"🔞 MPAA Rating added for {title}: {data['rating']}")
    else:
        print(f"⚠️ No rating found for {title}")

    print(f"✅ Finished: {title}\n")

async def enrich_epg(input_file, output_file, api_key):
    tree = ET.parse(input_file)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        tasks = [
            process_programme(session, p, api_key)
            for p in root.findall("programme")
        ]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"📺 EPG saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 script.py epg.xml epg_updated.xml TMDB_API_KEY")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2], sys.argv[3]))
