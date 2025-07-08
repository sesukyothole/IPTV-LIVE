import os
import json
import time
import re
import requests
import xml.etree.ElementTree as ET

API_KEY = os.environ.get("TMDB_API_KEY")
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_desc_cache.json"

TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_TV_DETAILS_URL = "https://api.themoviedb.org/3/tv/"
TMDB_MOVIE_DETAILS_URL = "https://api.themoviedb.org/3/movie/"

# Optional: Filter specific channel IDs (set to [] to process all)
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

# Load or create cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

def clean_title(title):
    title = re.sub(r"\(\d{4}\)", "", title)
    title = re.split("[-:]", title)[0]
    return title.strip()

def search_tmdb(title):
    if title in poster_cache:
        print(f"⚡ Cache hit: {title}")
        return poster_cache[title]

    print(f"🔍 Searching TMDb for: {title}")
    data = {
        "poster": None,
        "genres": [],
        "description": None
    }

    # Try TV show
    res = requests.get(TMDB_SEARCH_TV_URL, params={"api_key": API_KEY, "query": title})
    if res.status_code == 200:
        results = res.json().get("results", [])
        if results:
            item = results[0]
            data["poster"] = TMDB_IMAGE_URL + item["poster_path"] if item.get("poster_path") else None
            details = requests.get(f"{TMDB_TV_DETAILS_URL}{item['id']}", params={"api_key": API_KEY}).json()
            data["genres"] = [g["name"] for g in details.get("genres", [])]
            data["description"] = details.get("overview")
            poster_cache[title] = data
            return data

    # Try Movie
    res = requests.get(TMDB_SEARCH_MOVIE_URL, params={"api_key": API_KEY, "query": title})
    if res.status_code == 200:
        results = res.json().get("results", [])
        if results:
            item = results[0]
            data["poster"] = TMDB_IMAGE_URL + item["poster_path"] if item.get("poster_path") else None
            details = requests.get(f"{TMDB_MOVIE_DETAILS_URL}{item['id']}", params={"api_key": API_KEY}).json()
            data["genres"] = [g["name"] for g in details.get("genres", [])]
            data["description"] = details.get("overview")
            poster_cache[title] = data
            return data

    print(f"❌ No poster or data found for: {title}")
    poster_cache[title] = data
    return data

def enrich_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    total = len(root.findall("programme"))
    count = 0

    for programme in root.findall("programme"):
        channel_id = programme.get("channel")
        title_elem = programme.find("title")
        if not title_elem:
            continue

        if TARGET_CHANNELS and channel_id not in TARGET_CHANNELS:
            continue

        title = title_elem.text
        clean = clean_title(title)

        print(f"\n➡️ Processing: {title}")
        result = search_tmdb(clean)

        # Add portrait poster
        if result["poster"]:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", result["poster"])
            print(f"🖼️ Poster added")

        # Add genres
        if result["genres"]:
            for genre in result["genres"]:
                cat = ET.SubElement(programme, "category")
                cat.text = genre
            print(f"🎯 Genres added: {', '.join(result['genres'])}")
        else:
            print("⚠️ No genres found")

        # Add description
        if result["description"]:
            desc = ET.SubElement(programme, "desc")
            desc.text = result["description"]
            print(f"📝 Description added")
        else:
            print("⚠️ No description found")

        count += 1
        time.sleep(0.25)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(poster_cache, f, indent=2)

    print(f"\n✅ Done! Processed {count} programs. Saved to {output_file}")

if __name__ == "__main__":
    enrich_epg(INPUT_FILE, OUTPUT_FILE)
