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

async def search_tmdb(session, title, api_key):
    params = {"api_key": api_key, "query": title}
    movie_data = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    tv_data = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)

    result = {
        "poster": None,
        "description": None,
        "genres": [],
        "rating": "Not Rated"
    }

    show = None
    media_type = ""

    if movie_data.get("results"):
        show = movie_data["results"][0]
        media_type = "movie"
    elif tv_data.get("results"):
        show = tv_data["results"][0]
        media_type = "tv"

    if show:
        show_id = show["id"]
        result["poster"] = TMDB_IMAGE_BASE + (show.get("poster_path") or "")
        result["description"] = show.get("overview", "")

        if media_type == "movie":
            full = await fetch_json(session, f"{TMDB_BASE}/movie/{show_id}", {"api_key": api_key})
        else:
            full = await fetch_json(session, f"{TMDB_BASE}/tv/{show_id}", {"api_key": api_key})

        genre_names = [g["name"] for g in full.get("genres", [])]
        result["genres"] = genre_names

        for r in full.get("release_dates" if media_type == "movie" else "content_ratings", {}).get("results", []):
            if r.get("iso_3166_1") == "US":
                if media_type == "movie":
                    result["rating"] = r.get("release_dates", [{}])[0].get("certification", "Not Rated")
                else:
                    result["rating"] = r.get("rating", "Not Rated")

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

    # Remove old ratings
    for old_rating in programme.findall("rating"):
        programme.remove(old_rating)

    # MPAA Rating
    rating_el = ET.SubElement(programme, "rating")
    rating_el.set("system", "MPAA")
    value_el = ET.SubElement(rating_el, "value")
    value_el.text = data["rating"]
    print(f"🔞 Rating added for {title}: {data['rating']}")
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
    print(f"📺 Enriched EPG written to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 script.py input.xml output.xml TMDB_API_KEY")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2], sys.argv[3]))
