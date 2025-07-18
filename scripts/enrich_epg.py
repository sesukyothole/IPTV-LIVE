import os
import asyncio
import aiohttp
import xml.etree.ElementTree as ET

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
EPG_INPUT_FILE = os.getenv("EPG_INPUT_FILE", "guide.xml")
EPG_OUTPUT_FILE = os.getenv("EPG_OUTPUT_FILE", "guide_enriched.xml")
EPG_LANGUAGE = os.getenv("EPG_LANGUAGE", "en")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"

if not TMDB_API_KEY:
    raise EnvironmentError("TMDB_API_KEY environment variable is not set.")

async def fetch_tmdb(session, title):
    params = {
        "api_key": TMDB_API_KEY,
        "language": EPG_LANGUAGE,
        "query": title
    }
    async with session.get(TMDB_SEARCH_URL, params=params) as response:
        if response.status == 200:
            data = await response.json()
            return data.get("results", [])
        return []

async def enrich_programme(session, programme):
    title_elem = programme.find("title")
    if title_elem is None or not title_elem.text:
        return

    title = title_elem.text.strip()
    results = await fetch_tmdb(session, title)
    for item in results:
        backdrop_path = item.get("backdrop_path")
        if backdrop_path:
            icon = ET.SubElement(programme, "icon")
            icon.set("src", f"{TMDB_IMAGE_BASE}{backdrop_path}")
            return
    print(f"No landscape poster found for: {title}")

async def main():
    tree = ET.parse(EPG_INPUT_FILE)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        tasks = [enrich_programme(session, p) for p in programmes]
        await asyncio.gather(*tasks)

    tree.write(EPG_OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Enriched EPG written to {EPG_OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())