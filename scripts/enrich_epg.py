import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import logging
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def fetch_tmdb_info(session, title, language):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": language,
    }
    async with session.get(TMDB_SEARCH_URL, params=params) as response:
        if response.status != 200:
            logging.warning(f"TMDb search failed for '{title}' with status {response.status}")
            return None
        data = await response.json()
        if not data["results"]:
            return None
        for result in data["results"]:
            if result.get("backdrop_path"):
                return TMDB_IMAGE_BASE_URL + result["backdrop_path"]
        return None


async def enrich_programme(programme, session, language, landscape_only):
    title_elem = programme.find("title")
    if title_elem is None or not title_elem.text:
        return

    title = title_elem.text
    existing_icon = programme.find("icon")
    if existing_icon is not None:
        return  # Skip if icon already exists

    logging.info(f"Looking up: {title}")
    image_url = await fetch_tmdb_info(session, title, language)
    if image_url:
        if landscape_only:
            # We only want landscape images, assume w500 backdrop is landscape
            icon = ET.SubElement(programme, "icon")
            icon.set("src", image_url)
            logging.info(f"Added poster for: {title}")
        else:
            logging.info(f"Image found but not adding due to landscape_only={landscape_only}")
    else:
        logging.warning(f"No image found for: {title}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Input EPG XML file")
    parser.add_argument("output_file", help="Output enriched EPG XML file")
    parser.add_argument("--language", default="en", help="TMDb language (default: en)")
    parser.add_argument("--target-channels", nargs="*", help="List of channel IDs to enrich")
    parser.add_argument("--landscape-only", action="store_true", help="Only use landscape (backdrop) posters")
    parser.add_argument("--async", dest="use_async", action="store_true", help="Enable async mode")
    args = parser.parse_args()

    logging.info("Parsing XML...")
    tree = ET.parse(args.input_file)
    root = tree.getroot()

    programmes = root.findall("programme")
    if args.target_channels:
        programmes = [p for p in programmes if p.get("channel") in args.target_channels]

    async with aiohttp.ClientSession() as session:
        tasks = [
            enrich_programme(p, session, args.language, args.landscape_only)
            for p in programmes
        ]
        await asyncio.gather(*tasks)

    logging.info(f"Writing enriched EPG to {args.output_file}...")
    tree.write(args.output_file, encoding="utf-8", xml_declaration=True)
    logging.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())