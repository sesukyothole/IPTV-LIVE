import asyncio
import logging
import os
import xml.etree.ElementTree as ET
from aiohttp import ClientSession
import yaml

# --- Configuration ---
CONFIG_FILE = "enrich_epg_config.yml"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_epg")

# --- Load Config ---
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)
else:
    logger.warning(f"No {CONFIG_FILE} found, using hardcoded values.")
    config = {
        "input_file": "epg.xml",
        "output_file": "epg_enriched.xml",
        "language": "en",
        "target_channels": [
            "403788", "403674", "403837", "403794",
            "403620", "403772", "403655", "403847", "403576"
        ],
        "landscape_only": True
    }

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    raise EnvironmentError("TMDB_API_KEY environment variable not set.")

BASE_TMDB_SEARCH = "https://api.themoviedb.org/3/search/multi"
BASE_TMDB_IMAGE = "https://image.tmdb.org/t/p/w780"

# --- Async Fetch Poster ---
async def fetch_poster(title, session, language="en", landscape_only=True):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": language
    }
    async with session.get(BASE_TMDB_SEARCH, params=params) as resp:
        if resp.status != 200:
            logger.warning(f"Failed to fetch TMDb data for {title} (status {resp.status})")
            return None

        data = await resp.json()
        results = data.get("results", [])
        for item in results:
            backdrop = item.get("backdrop_path")
            if backdrop and landscape_only:
                logger.info(f"Found landscape poster for {title}")
                return BASE_TMDB_IMAGE + backdrop
        return None

# --- Main Processing ---
async def enrich_epg():
    input_file = config["input_file"]
    output_file = config["output_file"]
    language = config.get("language", "en")
    landscape_only = config.get("landscape_only", True)
    target_channels = config.get("target_channels", [])

    logger.info(f"Parsing EPG from {input_file}")
    tree = ET.parse(input_file)
    root = tree.getroot()

    async with ClientSession() as session:
        for programme in root.findall("programme"):
            channel = programme.attrib.get("channel", "")
            if target_channels and channel not in target_channels:
                continue

            title_el = programme.find("title")
            if title_el is None:
                continue
            title = title_el.text
            logger.info(f"Processing: {title} (Channel {channel})")

            poster_url = await fetch_poster(title, session, language, landscape_only)
            if poster_url:
                icon_el = ET.Element("icon")
                icon_el.attrib["src"] = poster_url
                programme.append(icon_el)

    logger.info(f"Writing enriched EPG to {output_file}")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    asyncio.run(enrich_epg())