import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
from typing import List

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w1280"

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Input EPG XML file")
    parser.add_argument("output_file", help="Output EPG XML file")
    parser.add_argument("--async", dest="use_async", action="store_true", help="Use async fetching")
    parser.add_argument("--landscape-only", action="store_true", help="Only use landscape (backdrop) images")
    parser.add_argument("--language", default="en", help="TMDb language (default: en)")
    parser.add_argument("--target-channels", nargs="+", help="Only update programs from these channel IDs")
    return parser.parse_args()

async def fetch_poster(session, title, language, landscape_only):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": language
    }
    async with session.get(TMDB_SEARCH_URL, params=params) as resp:
        data = await resp.json()
        for result in data.get("results", []):
            if landscape_only and result.get("backdrop_path"):
                return TMDB_IMAGE_BASE + result["backdrop_path"]
            elif not landscape_only and result.get("poster_path"):
                return TMDB_IMAGE_BASE + result["poster_path"]
        return None

async def enrich_programs(programs: List[ET.Element], language: str, landscape_only: bool):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for prog in programs:
            title_elem = prog.find("title")
            if title_elem is not None:
                title = title_elem.text
                tasks.append(fetch_poster(session, title, language, landscape_only))
            else:
                tasks.append(asyncio.sleep(0))  # placeholder
        posters = await asyncio.gather(*tasks)

        for prog, poster_url in zip(programs, posters):
            if poster_url:
                # Remove old icon
                for old_icon in prog.findall("icon"):
                    prog.remove(old_icon)
                ET.SubElement(prog, "icon", {"src": poster_url})

def enrich_sync(programs: List[ET.Element], language: str, landscape_only: bool):
    import requests
    for prog in programs:
        title_elem = prog.find("title")
        if title_elem is None:
            continue
        title = title_elem.text
        params = {
            "api_key": TMDB_API_KEY,
            "query": title,
            "language": language
        }
        resp = requests.get(TMDB_SEARCH_URL, params=params)
        if resp.status_code == 200:
            data = resp.json()
            poster_url = None
            for result in data.get("results", []):
                if landscape_only and result.get("backdrop_path"):
                    poster_url = TMDB_IMAGE_BASE + result["backdrop_path"]
                    break
                elif not landscape_only and result.get("poster_path"):
                    poster_url = TMDB_IMAGE_BASE + result["poster_path"]
                    break
            if poster_url:
                for old_icon in prog.findall("icon"):
                    prog.remove(old_icon)
                ET.SubElement(prog, "icon", {"src": poster_url})

def main():
    args = parse_args()

    tree = ET.parse(args.input_file)
    root = tree.getroot()

    if args.target_channels:
        allowed_channels = set(args.target_channels)
        programs = [prog for prog in root.findall("programme")
                    if prog.get("channel") in allowed_channels]
    else:
        programs = root.findall("programme")

    if args.use_async:
        asyncio.run(enrich_programs(programs, args.language, args.landscape_only))
    else:
        enrich_sync(programs, args.language, args.landscape_only)

    tree.write(args.output_file, encoding="utf-8", xml_declaration=True)
    print(f"Enriched EPG saved to {args.output_file}")

if __name__ == "__main__":
    main()