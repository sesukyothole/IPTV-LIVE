import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import xmltodict
from tqdm.asyncio import tqdm
import logging
import time

TMDB_API_KEY = "YOUR_TMDB_API_KEY_HERE"
INPUT_EPG_FILE = "epg.xml"
OUTPUT_EPG_FILE = "epg_enriched.xml"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"  # landscape size

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "403847", "403772", "403576", "403926", 
    "403461"
}

# Manual TMDb overrides
MANUAL_ID_OVERRIDES = {
    "Jessie": {"type": "tv", "id": 38974},
    "Big City Greens": {"type": "tv", "id": 80587},
    "Kiff": {"type": "tv", "id": 127706},
    "Zombies": {"type": "movie", "id": 483980},
    "Bluey": {"type": "tv", "id": 82728},
    "Disney Jr's Ariel": {"type": "tv", "id": 228669},
    "Gravity Falls": {"type": "tv", "id": 40075},
    "Monsters, Inc.": {"type": "movie", "id": 585},
    "The Incredibles": {"type": "movie", "id": 9806},
    "SpongeBob SquarePants": {"type": "tv", "id": 387},
    "Peppa Pig": {"type": "tv", "id": 12225},
    "PAW Patrol": {"type": "tv", "id": 57532},
    "Rubble & Crew": {"type": "tv", "id": 214875},
    "Gabby's Dollhouse": {"type": "tv", "id": 111474},
    "black-ish": {"type": "tv", "id": 61381},
    "Phineas and Ferb": {"type": "tv", "id": 1877},
    "Win or Lose": {"type": "tv", "id": 114500},
    "Friends": {"type": "tv", "id": 1668},
    "Primos": {"type": "tv", "id": 204139},
    "DuckTales": {"type": "tv", "id": 72350},
    "Mulan": {"type": "movie", "id": 337401},
    "Moana": {"type": "movie", "id": 277834},
    "Modern Family": {"type": "tv", "id": 1421},
    "Henry Danger": {"type": "tv", "id": 61852},
    "The Really Loud House": {"type": "tv", "id": 211779}
}

# Setup logger
logging.basicConfig(
    filename='enrich_epg_landscape.log',
    filemode='w',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO
)

# Async TMDb request
async def fetch_tmdb_data(session, title):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "en-US"
    }
    try:
        async with session.get(TMDB_SEARCH_URL, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("results"):
                    return data["results"][0]  # Take top result
            logging.warning(f"No result for '{title}'")
    except Exception as e:
        logging.error(f"TMDb request failed for '{title}': {e}")
    return None

# Enrichment task
async def enrich_programme(session, programme):
    title_elem = programme.find("title")
    if title_elem is None:
        return

    title = title_elem.text
    tmdb_data = await fetch_tmdb_data(session, title)

    if not tmdb_data:
        return

    # Add poster
    if 'backdrop_path' in tmdb_data and tmdb_data['backdrop_path']:
        ET.SubElement(programme, "icon", {"src": TMDB_IMAGE_BASE_URL + tmdb_data['backdrop_path']})

    # Add description
    if 'overview' in tmdb_data:
        desc = ET.SubElement(programme, "desc", {"lang": "en"})
        desc.text = tmdb_data['overview']

    # Add genre(s)
    if 'genre_ids' in tmdb_data:
        for genre in tmdb_data['genre_ids']:
            genre_elem = ET.SubElement(programme, "category", {"lang": "en"})
            genre_elem.text = str(genre)  # Or map to genre name if needed

    # Add year
    if 'first_air_date' in tmdb_data and tmdb_data['first_air_date']:
        year = tmdb_data['first_air_date'].split("-")[0]
        ET.SubElement(programme, "date").text = year

    # Add age rating (optional, not always available)
    if tmdb_data.get('adult') is not None:
        rating = "TV-MA" if tmdb_data['adult'] else "TV-G"
        rating_elem = ET.SubElement(programme, "rating", {"system": "MPAA"})
        ET.SubElement(rating_elem, "value").text = rating

    logging.info(f"Enriched: {title}")

# Load EPG
def load_epg(file_path):
    tree = ET.parse(file_path)
    return tree, tree.getroot()

# Save EPG
def save_epg(tree, file_path):
    tree.write(file_path, encoding="utf-8", xml_declaration=True)
    logging.info(f"Saved enriched EPG to {file_path}")

# Main
async def main():
    logging.info("Starting enrichment process...")
    start_time = time.time()

    tree, root = load_epg(INPUT_EPG_FILE)
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await tqdm.gather(*(enrich_programme(session, p) for p in programmes))

    save_epg(tree, OUTPUT_EPG_FILE)
    logging.info(f"Completed in {time.time() - start_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())