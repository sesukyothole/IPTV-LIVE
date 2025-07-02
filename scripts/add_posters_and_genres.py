import requests
import xml.etree.ElementTree as ET
import os
import time
import json

# TMDb API Key from GitHub Secrets
API_KEY = os.environ['TMDB_API_KEY']

# Channels to process
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]

# TMDb URLs
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Files
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"
CACHE_FILE = "poster_genre_cache.json"

# Requests header
HEADERS = {
    'User-Agent': 'EPGPosterBot/1.0'
}

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
    result_data = {'landscape': None, 'portrait': None, 'genres': []}

    try:
        response = requests.get(TMDB_SEARCH_TV_URL, params={"api_key": API_KEY, "query": query}, headers=HEADERS)
        response.raise_for_status()
        results = response.json().get('results', [])

        if results:
            result = results[0]
            if result.get('backdrop_path'):
                result_data['landscape'] = TMDB_IMAGE_URL + result['backdrop_path']
            if result.get('poster_path'):
                result_data['portrait'] = TMDB_IMAGE_URL + result['poster_path']
            result_data['genres'] = get_genres(result.get('id'), content_type='tv')
            poster_cache[query] = result_data
            return result_data

        # If not found as TV Show, try searching Movies
        response = requests.get(TMDB_SEARCH_MOVIE_URL, params={"api_key": API_KEY, "query": query}, headers=HEADERS)
        response.raise_for_status()
        results = response.json().get('results', [])

        if results:
            result = results[0]
            if result.get('backdrop_path'):
                result_data['landscape'] = TMDB_IMAGE_URL + result['backdrop_path']
            if result.get('poster_path'):
                result_data['portrait'] = TMDB_IMAGE_URL + result['poster_path']
            result_data['genres'] = get_genres(result.get('id'), content_type='movie')
            poster_cache[query] = result_data
            return result_data

    except Exception as e:
        print(f"❌ TMDb request failed: {e}")

    poster_cache[query] = result_data
    return result_data

def get_genres(content_id, content_type='tv'):
    if content_id is None:
        return []
    url = f"https://api.themoviedb.org/3/{content_type}/{content_id}"
    try:
        response = requests.get(url, params={"api_key": API_KEY}, headers=HEADERS)
        response.raise_for_status()
        genres = response.json().get('genres', [])
        return [genre['name'] for genre in genres]
    except Exception as e:
        print(f"❌ Failed to fetch genres: {e}")
        return []

def add_posters_and_genres_to_epg(input_file, output_file):
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

            result_data = search_tmdb(title)

            if result_data['landscape']:
                icon_landscape = ET.SubElement(programme, 'icon')
                icon_landscape.set('src', result_data['landscape'])
                print(f"✅ Landscape poster added: {result_data['landscape']}")

            if result_data['portrait']:
                icon_portrait = ET.SubElement(programme, 'icon')
                icon_portrait.set('src', result_data['portrait'])
                print(f"✅ Portrait poster added: {result_data['portrait']}")

            if result_data['genres']:
                for genre in result_data['genres']:
                    category = ET.SubElement(programme, 'category')
                    category.text = genre
                print(f"🎯 Genres added: {', '.join(result_data['genres'])}")
            else:
                print(f"❌ No genres found for: {title}")

            time.sleep(0.5)  # TMDb rate limit protection

    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"\n✅ EPG updated and saved to {output_file}")

    # Save updated poster cache
    with open(CACHE_FILE, 'w') as f:
        json.dump(poster_cache, f)
    print("✅ Poster and genre cache saved successfully!")

if __name__ == "__main__":
    add_posters_and_genres_to_epg(INPUT_FILE, OUTPUT_FILE)
