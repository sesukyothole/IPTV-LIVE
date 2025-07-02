import xml.etree.ElementTree as ET
import requests
import os
import time
import json

# Load TMDb API Key from GitHub Secrets
API_KEY = os.environ['TMDB_API_KEY']
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w500'

# Channels you want to process
target_channels = {'403788', '403674', '403837', '403794', '403620', '403655', '8359', '403847', '403461', '403576'}  # Add your channel IDs here

# Load EPG XML
tree = ET.parse('epg.xml')
root = tree.getroot()

# Caching to avoid duplicate TMDb requests
cache = {}

# Load cache from file if exists
if os.path.exists('poster_cache.json'):
    with open('poster_cache.json', 'r') as f:
        cache = json.load(f)

def search_tmdb(title):
    if title in cache:
        return cache[title]

    print(f'Searching TMDb for: {title}')

    # Try TV first
    response = requests.get(f'https://api.themoviedb.org/3/search/tv', params={'api_key': API_KEY, 'query': title})
    data = response.json()

    if data.get('results'):
        poster_path = data['results'][0].get('poster_path')
        if poster_path:
            poster_url = f'{IMAGE_BASE_URL}{poster_path}'
            cache[title] = poster_url
            time.sleep(0.25)  # Respect TMDb rate limits
            return poster_url

    # Try Movie if TV not found
    response = requests.get(f'https://api.themoviedb.org/3/search/movie', params={'api_key': API_KEY, 'query': title})
    data = response.json()

    if data.get('results'):
        poster_path = data['results'][0].get('poster_path')
        if poster_path:
            poster_url = f'{IMAGE_BASE_URL}{poster_path}'
            cache[title] = poster_url
            time.sleep(0.25)
            return poster_url

    # If not found
    cache[title] = None
    return None

# Process each programme
for programme in root.findall('programme'):
    channel_id = programme.get('channel')
    if channel_id not in target_channels:
        continue

    title_element = programme.find('title')
    if title_element is None:
        continue

    title = title_element.text
    if not title:
        continue

    poster_url = search_tmdb(title)

    if poster_url:
        # Add <icon> to the programme
        icon_element = ET.Element('icon')
        icon_element.set('src', poster_url)
        programme.append(icon_element)
        print(f'Poster added: {title}')
    else:
        print(f'Poster not found: {title}')

# Save updated XML
tree.write('epg_updated.xml', encoding='utf-8')

# Save cache to speed up future runs
with open('poster_cache.json', 'w') as f:
    json.dump(cache, f)

print('EPG updated successfully.')
