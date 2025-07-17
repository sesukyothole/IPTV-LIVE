import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"  # Landscape poster size

HEADERS = {
    "Authorization": f"Bearer {TMDB_API_KEY}",
    "Content-Type": "application/json;charset=utf-8",
}

async def fetch_tmdb_poster(session, title, language):
    query_url = f"{TMDB_BASE_URL}/search/movie?query={title}&language={language}"

    async with session.get(query_url) as response:
        if response.status != 200:
            return None
        data = await response.json()
        results = data.get("results", [])
        if results:
            backdrop_path = results[0].get("backdrop_path")
            return f"{TMDB_IMAGE_BASE}{backdrop_path}" if backdrop_path else None
    return None

async def enrich_programme(programme, session, language):
    title_elem = programme.find("title")
    if title_elem is None or not title_elem.text:
        return

    title = title_elem.text.strip()
    poster_url = await fetch_tmdb_poster(session, title, language)

    if poster_url:
        icon_elem = programme.find("icon")
        if icon_elem is None:
            icon_elem = ET.SubElement(programme, "icon")
        icon_elem.set("src", poster_url)

async def enrich_epg(input_file, output_file, language, target_channels):
    tree = ET.parse(input_file)
    root = tree.getroot()

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = []

        for programme in root.findall("programme"):
            channel = programme.get("channel")
            if channel and int(channel) in target_channels:
                tasks.append(enrich_programme(programme, session, language))

        await asyncio.gather(*tasks)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    parser.add_argument("--async", action="store_true", dest="use_async", help="Use async mode")
    parser.add_argument("--landscape-only", action="store_true", help="Only use landscape posters")
    parser.add_argument("--language", default="en", help="Language code for TMDb")
    parser.add_argument("--target-channels", nargs="+", type=int, default=[], help="Channel IDs to target")

    args = parser.parse_args()

    if not TMDB_API_KEY:
        raise EnvironmentError("TMDB_API_KEY is not set")

    asyncio.run(enrich_epg(args.input_file, args.output_file, args.language, args.target_channels))

if __name__ == "__main__":
    main()