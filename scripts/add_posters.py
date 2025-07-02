import xml.etree.ElementTree as ET
import requests
import os
import time

API_KEY = os.environ['TMDB_API_KEY']

# TMDb API Base URLs
SEARCH_MOVIE_URL = 'https://api.themoviedb.org/3/search/movie'
SEARCH_TV_URL = 'https://api.themoviedb.org/3/search/tv'
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w780'  # Landscape resolution

# Cache to avoid hitting the API for the same title
poster_cache = {}

def search_tmdb(title):
    """Search for a poster from TMDb (prefers backdrop, fallback to poster)"""
    if title in poster_cache:
        return poster_cache[title]

    print(f"Searching TMDb for: {title}")

    # Try TV Show first
    response = requests.get(SEARCH_TV_URL, params={'api_key': API_KEY, 'query': title})
    data = response.json()

    if data['results']:
        result = data['results'][0]
        poster_url = None
        if result.get('backdrop_path'):
            poster_url = IMAGE_BASE_URL + result['backdrop_path']
        elif result.get('poster_path'):
            poster_url = IMAGE_BASE_URL + result['poster_path']

        poster_cache[title] = poster_url
        return poster_url

    # If not found as TV Show, try as Movie
    response = requests.get(SEARCH_MOVIE_URL, params={'api_key': API_KEY, 'query': title})
    data = response.json()

    if data['results']:
        result = data['results'][0]
        poster_url = None
        if result.get('backdrop_path'):
            poster_url = IMAGE_BASE_URL + result['backdrop_path']
        elif result.get('poster_path'):
            poster_url = IMAGE_BASE_URL + result['poster_path']

        poster_cache[title] = poster_url
        return poster_url

    # If nothing found, return None
    poster_cache[title] = None
    return None

def add_posters_to_epg(epg_file, output_file):
    tree = ET.parse(epg_file)
    root = tree.getroot()

    for programme in root.findall('programme'):
        title_elem = programme.find('title')
        if title_elem is not None:
            title = title_elem.text
            poster_url = search_tmdb(title)

            if poster_url:
                # Add poster to programme
                icon_elem = ET.Element('icon')
                icon_elem.set('src', poster_url)
                programme.append(icon_elem)

            # Optional: wait 250ms between requests to be nice to the API
            time.sleep(0.25)

    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ Posters added! Updated EPG saved as: {output_file}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python add_posters.py input_epg.xml output_epg.xml")
        exit(1)

    input_epg = sys.argv[1]
    output_epg = sys.argv[2]

    add_posters_to_epg(input_epg, output_epg)
