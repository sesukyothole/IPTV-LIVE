import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
from aiohttp import ClientSession
from tqdm.asyncio import tqdm

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"  # Landscape size

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620", "403772", "403655", "403847", "403576"
}


async def fetch_landscape_poster(session: ClientSession, title: str) -> str | None:
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "en"
    }
    try:
        async with session.get(TMDB_SEARCH_URL, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get("results", [])
                for result in results:
                    if result.get("backdrop_path"):
                        return f"{TMDB_IMAGE_BASE_URL}{result['backdrop_path']}"
    except Exception as e:
        print(f"Error fetching for {title}: {e}")
    return None


async def enrich_program(session: ClientSession, programme, semaphore):
    channel = programme.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    title_elem = programme.find("title")
    if title_elem is None:
        return

    title = title_elem.text
    async with semaphore:
        poster_url = await fetch_landscape_poster(session, title)
    if poster_url:
        icon_elem = programme.find("icon")
        if icon_elem is None:
            icon_elem = ET.SubElement(programme, "icon")
        icon_elem.set("src", poster_url)


async def main(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    programmes = root.findall("programme")
    semaphore = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        tasks = [
            enrich_program(session, programme, semaphore)
            for programme in programmes
        ]
        await tqdm.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich EPG XML with landscape posters from TMDb")
    parser.add_argument("input_file", help="Input EPG XML file")
    parser.add_argument("output_file", help="Output enriched XML file")
    args = parser.parse_args()

    if not TMDB_API_KEY:
        print("Error: TMDB_API_KEY environment variable not set.")
        exit(1)

    asyncio.run(main(args.input_file, args.output_file))