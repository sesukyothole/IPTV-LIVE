import aiohttp
import asyncio
import async_timeout
import xml.etree.ElementTree as ET
import os
import json

API_KEY = os.environ["TMDB_API_KEY"]
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "tmdb_cache.json"
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        tmdb_cache = json.load(f)
else:
    tmdb_cache = {}

async def fetch_json(session, url, params):
    async with async_timeout.timeout(10):
        async with session.get(url, params=params) as response:
            return await response.json()

async def get_tmdb_data(session, title):
    if title in tmdb_cache:
        print(f"⚡ Cached: {title}")
        return tmdb_cache[title]

    print(f"\n🔎 Searching TMDb for: {title}")
    data = {"poster": None, "overview": None, "genres": [], "rating": None}

    # 1. Try TV
    search_tv = await fetch_json(session, "https://api.themoviedb.org/3/search/tv", {"api_key": API_KEY, "query": title})
    if search_tv.get("results"):
        tv = search_tv["results"][0]
        tv_id = tv["id"]
        data["poster"] = TMDB_IMAGE + tv["poster_path"] if tv.get("poster_path") else None
        data["overview"] = tv.get("overview")

        # Genres
        tv_details = await fetch_json(session, f"https://api.themoviedb.org/3/tv/{tv_id}", {"api_key": API_KEY})
        data["genres"] = [g["name"] for g in tv_details.get("genres", [])]

        # TV Ratings
        ratings = await fetch_json(session, f"https://api.themoviedb.org/3/tv/{tv_id}/content_ratings", {"api_key": API_KEY})
        for r in ratings.get("results", []):
            if r.get("iso_3166_1") == "US":
                data["rating"] = r.get("rating")
                data["rating_system"] = "US-TV"
                break

        tmdb_cache[title] = data
        return data

    # 2. Try Movie
    search_movie = await fetch_json(session, "https://api.themoviedb.org/3/search/movie", {"api_key": API_KEY, "query": title})
    if search_movie.get("results"):
        movie = search_movie["results"][0]
        movie_id = movie["id"]
        data["poster"] = TMDB_IMAGE + movie["poster_path"] if movie.get("poster_path") else None
        data["overview"] = movie.get("overview")

        # Genres
        movie_details = await fetch_json(session, f"https://api.themoviedb.org/3/movie/{movie_id}", {"api_key": API_KEY})
        data["genres"] = [g["name"] for g in movie_details.get("genres", [])]

        # Movie Ratings
        ratings = await fetch_json(session, f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates", {"api_key": API_KEY})
        for r in ratings.get("results", []):
            if r.get("iso_3166_1") == "US":
                for release in r.get("release_dates", []):
                    cert = release.get("certification")
                    if cert:
                        data["rating"] = cert
                        data["rating_system"] = "MPAA"
                        break
                break

        tmdb_cache[title] = data
        return data

    print("🚫 No data found.")
    return data

async def process_programme(session, programme):
    channel_id = programme.get("channel")
    title_element = programme.find("title")
    if channel_id not in TARGET_CHANNELS or title_element is None:
        return

    title = title_element.text.strip()
    print(f"\n🎬 Title: {title}")
    data = await get_tmdb_data(session, title)

    if data["poster"]:
        ET.SubElement(programme, "icon", {"src": data["poster"]})
        print("🖼️ Poster added")
    else:
        print("🚫 No poster found")

    if data["overview"]:
        desc = programme.find("desc")
        if desc is None:
            desc = ET.SubElement(programme, "desc", {"lang": "en"})
        desc.text = data["overview"]
        print("📃 Description added")
    else:
        print("🚫 No description found")

    if data["genres"]:
        for genre in data["genres"]:
            ET.SubElement(programme, "category").text = genre
        print(f"🎯 Genres added: {', '.join(data['genres'])}")
    else:
        print("🚫 No genres found")

    if data.get("rating"):
        rating = ET.SubElement(programme, "rating", {"system": data.get("rating_system", "MPAA")})
        ET.SubElement(rating, "value").text = data["rating"]
        print(f"🔞 Rating added: {data['rating']}")
    else:
        print("🚫 No rating found")

async def main():
    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()
    async with aiohttp.ClientSession() as session:
        tasks = [process_programme(session, p) for p in root.findall("programme")]
        await asyncio.gather(*tasks)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG saved as {OUTPUT_FILE}")

    with open(CACHE_FILE, 'w') as f:
        json.dump(tmdb_cache, f)
    print("💾 Cache saved")

if __name__ == "__main__":
    asyncio.run(main())
