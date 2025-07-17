import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import logging

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"  # Landscape size

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Input EPG XML file")
    parser.add_argument("output_file", help="Output enriched EPG XML file")
    parser.add_argument("--language", default="en", help="Preferred language (default: en)")
    parser.add_argument("--target-channels", nargs="+", required=True, help="List of target channel IDs")
    parser.add_argument("--landscape-only", action="store_true", help="Use only landscape posters")
    parser.add_argument("--async", dest="use_async", action="store_true", help="Enable asynchronous TMDB lookups")
    return parser.parse_args()


async def fetch_poster(session, title, language, landscape_only):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": language
    }
    async with session.get(TMDB_SEARCH_URL, params=params) as resp:
        if resp.status != 200:
            logging.warning(f"TMDb API failed for '{title}' with status {resp.status}")
            return None
        data = await resp.json()
        for result in data.get("results", []):
            backdrop = result.get("backdrop_path")
            poster = result.get("poster_path")
            if landscape_only and backdrop:
                return TMDB_IMAGE_BASE_URL + backdrop
            elif not landscape_only and (backdrop or poster):
                return TMDB_IMAGE_BASE_URL + (backdrop or poster)
    logging.info(f"No TMDb poster found for: {title}")
    return None


async def enrich_programme(programme, session, language, landscape_only):
    title_elem = programme.find("title")
    if title_elem is None:
        return

    title = title_elem.text
    existing_icon = programme.find("icon")
    if existing_icon is not None:
        return

    poster_url = await fetch_poster(session, title, language, landscape_only)
    if poster_url:
        icon = ET.SubElement(programme, "icon")
        icon.set("src", poster_url)
        logging.info(f"Poster added for: {title}")


async def enrich_epg_async(root, target_channels, language, landscape_only):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for prog in root.findall("programme"):
            channel_id = prog.get("channel")
            if channel_id in target_channels:
                tasks.append(enrich_programme(prog, session, language, landscape_only))
        await asyncio.gather(*tasks)


def enrich_epg_sync(root, target_channels, language, landscape_only):
    import requests

    def fetch_sync(title):
        params = {
            "api_key": TMDB_API_KEY,
            "query": title,
            "language": language
        }
        try:
            resp = requests.get(TMDB_SEARCH_URL, params=params)
            if resp.status_code != 200:
                logging.warning(f"TMDb API failed for '{title}' with status {resp.status_code}")
                return None
            data = resp.json()
            for result in data.get("results", []):
                backdrop = result.get("backdrop_path")
                poster = result.get("poster_path")
                if landscape_only and backdrop:
                    return TMDB_IMAGE_BASE_URL + backdrop
                elif not landscape_only and (backdrop or poster):
                    return TMDB_IMAGE_BASE_URL + (backdrop or poster)
        except Exception as e:
            logging.error(f"Error fetching poster for {title}: {e}")
        return None

    for prog in root.findall("programme"):
        channel_id = prog.get("channel")
        if channel_id not in target_channels:
            continue

        title_elem = prog.find("title")
        if title_elem is None or prog.find("icon") is not None:
            continue

        title = title_elem.text
        poster_url = fetch_sync(title)
        if poster_url:
            icon = ET.SubElement(prog, "icon")
            icon.set("src", poster_url)
            logging.info(f"Poster added for: {title}")


def main():
    args = parse_args()

    logging.info("Parsing EPG XML...")
    tree = ET.parse(args.input_file)
    root = tree.getroot()

    if args.use_async:
        logging.info("Using async mode for TMDb fetches...")
        asyncio.run(enrich_epg_async(root, args.target_channels, args.language, args.landscape_only))
    else:
        logging.info("Using sync mode for TMDb fetches...")
        enrich_epg_sync(root, args.target_channels, args.language, args.landscape_only)

    tree.write(args.output_file, encoding="utf-8", xml_declaration=True)
    logging.info(f"Enriched EPG saved to {args.output_file}")


if __name__ == "__main__":
    main()