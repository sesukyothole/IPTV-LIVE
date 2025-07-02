import requests
import xml.etree.ElementTree as ET
import os
import time

# Load TMDb API Key from GitHub Action Secrets
API_KEY = os.environ['TMDB_API_KEY']

# Define channels to process (you can add more channel IDs)
TARGET_CHANNELS = ["403788", "403674", "403837", "403794", "403620", "403655", "8359", "403847", "403461", "403576"]  # Example: Disney channels

# TMDb base URLs
TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

# Input and output file names
INPUT_FILE = "epg.xml"
OUTPUT_FILE = "epg_updated.xml"

def search_tmdb(query):
    # Try searching TV Shows first
    response = requests.get(TMDB_SEARCH_TV_URL, params={"api_key": API_KEY, "query": query})
    results = response.json().get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            return TMDB_IMAGE_URL + result['backdrop_path']
        elif result.get('poster_path'):
            return TMDB_IMAGE_URL + result['poster_path']

    # If not found as TV Show, try searching Movies
    response = requests.get(TMDB_SEARCH_MOVIE_URL, params={"api_key": API_KEY, "query": query})
    results = response.json().get('results', [])
    if results:
        result = results[0]
        if result.get('backdrop_path'):
            return TMDB_IMAGE_URL + result['backdrop_path']
        elif result.get('poster_path'):
            return TMDB_IMAGE_URL + result['poster_path']

    return None  # No poster found

def add_posters_to_epg(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    for programme in root.findall('programme'):
        channel_id = programme.get('channel')
        title_element = programme.find('title')

        if channel_id in TARGET_CHANNELS and title_element is not None:
            title = title_element.text
            print(f"Processing: {title}")

            icon_element = programme.find('icon')
            if icon_element is None:
                poster_url = search_tmdb(title)
                if poster_url:
                    icon = ET.SubElement(programme, 'icon')
                    icon.set('src', poster_url)
                    print(f"Poster found: {poster_url}")
                else:
                    print(f"No poster found for: {title}")
                time.sleep(0.5)  # TMDb rate limiting (optional)

    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"EPG updated and saved to {output_file}")

if __name__ == "__main__":
    add_posters_to_epg(INPUT_FILE, OUTPUT_FILE)
