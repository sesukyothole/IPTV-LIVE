import sys
import asyncio
import aiohttp
import xml.etree.ElementTree as ET

TMDB_API_KEY = sys.argv[3] if len(sys.argv) > 3 else os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w342"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

HEADERS = {"Accept": "application/json"}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        return await response.json()

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title}
    result = {}

    movie = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    tv = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)

    show = None
    is_movie = False
    if movie.get("results"):
        show = movie["results"][0]
        is_movie = True
    elif tv.get("results"):
        show = tv["results"][0]

    if not show:
        return None

    result["poster"] = TMDB_IMAGE_URL + show["poster_path"] if show.get("poster_path") else None
    result["description"] = show.get("overview", "").strip()
    result["genres"] = []

    if is_movie:
        detail = await fetch_json(session, f"{TMDB_BASE}/movie/{show['id']}", {"api_key": TMDB_API_KEY})
    else:
        detail = await fetch_json(session, f"{TMDB_BASE}/tv/{show['id']}", {"api_key": TMDB_API_KEY})

    result["genres"] = [g["name"] for g in detail.get("genres", [])]

    # Rating
    rating = None
    if is_movie:
        for country in detail.get("release_dates", {}).get("results", []):
            if country["iso_3166_1"] == "US":
                for release in country.get("release_dates", []):
                    rating = release.get("certification")
                    if rating:
                        break
    else:
        for country in detail.get("content_ratings", {}).get("results", []):
            if country["iso_3166_1"] == "US":
                rating = country.get("rating")
                break

    result["rating"] = rating or "Not Rated"

    return result

async def process_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel")

    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text.strip()
    print(f"🔍 Searching: {title}")

    try:
        data = await search_tmdb(session, title)
        if not data:
            print(f"❌ No data found for {title}")
            return

        if data["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", data["poster"])
            print(f"🖼️ Poster added for {title}")
        else:
            print(f"❌ Poster not found for {title}")

        if data["description"]:
            desc_el = programme.find("desc")
            if desc_el is None:
                desc_el = ET.SubElement(programme, "desc")
            desc_el.text = data["description"]
            print(f"📝 Description added for {title}")
        else:
            print(f"❌ Description not found for {title}")

        for genre in data["genres"]:
            cat = ET.SubElement(programme, "category")
            cat.text = genre
        print(f"🎭 Genres added for {title}: {', '.join(data['genres']) or 'None'}")

        if data["rating"]:
            desc_el = programme.find("desc")
            if desc_el is None:
                desc_el = ET.SubElement(programme, "desc")
                desc_el.text = f"[Rated {data['rating']}]"
            else:
                existing_desc = desc_el.text or ""
                desc_el.text = f"{existing_desc} [Rated {data['rating']}]"
            print(f"🎞️ Rating added for {title}: {data['rating']}")
        else:
            print(f"❌ No rating found for {title}")

        print(f"✅ Done processing: {title}\n")
    except Exception as e:
        print(f"⚠️ Error processing {title}: {e}")

async def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [process_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"📺 EPG written to {output_file}")

if __name__ == "__main__":
    import os
    if len(sys.argv) < 4:
        print("Usage: python3 script.py input.xml output.xml TMDB_API_KEY")
        sys.exit(1)
    asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
