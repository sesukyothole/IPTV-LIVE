import requests
import xml.etree.ElementTree as ET
import os
import time
import json

# TMDb API Key from GitHub Secrets
API_KEY = os.environ['TMDB_API_KEY']

# Channels to process
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]  # Add your channel IDs here

# TMDb URLs
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Files
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_cache.json"

# Load or create poster cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        poster_cache = json.load(f)
else:
    poster_cache = {}

def search_tmdb(query):
    if query in poster_cache:
        print(f"⚡ Cache hit for: {query}")
        return poster_cache[query]

    print(f"🔍 Searching TMDb for: {query}")

    # Search TV shows first
    response = requests.get(TMDB_SEARCH_TV_URL, params={"api_key": API_KEY, "query": query})
    results = response.json().get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            poster_url = TMDB_IMAGE_URL + result['backdrop_path']
            poster_cache[query] = poster_url
            return poster_url
        elif result.get('poster_path'):
            poster_url = TMDB_IMAGE_URL + result['poster_path']
            poster_cache[query] = poster_url
            return poster_url

    # Search Movies if not found as TV show
    response = requests.get(TMDB_SEARCH_MOVIE_URL, params={"api_key": API_KEY, "query": query})
    results = response.json().get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            poster_url = TMDB_IMAGE_URL + result['backdrop_path']
            poster_cache[query] = poster_url
            return poster_url
        elif result.get('poster_path'):
            poster_url = TMDB_IMAGE_URL + result['poster_path']
            poster_cache[query] = poster_url
            return poster_url

    # No poster found
    poster_cache[query] = None
    return None

def add_posters_to_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    total_programmes = len(root.findall('programme'))
    processed_count = 0

    for programme in root.findall('programme'):
        channel_id = programme.get('channel')
        title_element = programme.find('title')

        if channel_id in TARGET_CHANNELS and title_element is not None:
            processed_count += 1
            title = title_element.text
            print(f"➡️ [{processed_count}/{total_programmes}] Processing: {title}")

            icon_element = programme.find('icon')
            if icon_element is None:
                poster_url = search_tmdb(title)

                if poster_url:
                    icon = ET.SubElement(programme, 'icon')
                    icon.set('src', poster_url)
                    print(f"✅ Poster added for: {title} → {poster_url}")
                else:
                    print(f"❌ No poster found for: {title}")

                time.sleep(0.5)  # TMDb rate limit protection

    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"\n✅ EPG updated and saved to {output_file}")

    # Save updated poster cache
    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)
    print("✅ Poster cache saved successfully!")

if __name__ == "__main__":
    add_posters_to_epg(INPUT_FILE, OUTPUT_FILE)
