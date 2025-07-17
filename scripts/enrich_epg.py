import argparse
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import logging

# ----------------------------
# TMDb Configuration
# ----------------------------
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_URL = "https://api.themoviedb.org/3/{media_type}/{id}/images"
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w780"

# ----------------------------
# Logging Setup
# ----------------------------
logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
)
log = logging.getLogger("EPG-Enricher")

# ----------------------------
# CLI Argument Parser
# ----------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Enrich EPG with TMDb landscape posters")
    parser.add_argument("input_file", help="Input EPG XML file")
    parser.add_argument("output_file", help="Output EPG XML file")
    parser.add_argument("--language", default="en", help="Poster language (default: en)")
    parser.add_argument("--target-channels", nargs="+", required=True, help="Target channel IDs")
    return parser.parse_args()

# ----------------------------
# TMDb API Callers
# ----------------------------
async def search_tmdb(session, title):
    params = {"query": title, "include_adult": "false", "language": "en-US"}
    try:
        async with session.get(TMDB_SEARCH_URL, params=params) as res:
            if res.status != 200:
                log.warning(f"Search failed for '{title}': HTTP {res.status}")
                return None, None
            data = await res.json()
            if not data.get("results"):
                return None, None
            top = data["results"][0]
            return top["media_type"], top["id"]
    except Exception as e:
        log.error(f"TMDb search error: {e}")
        return None, None

async def get_landscape(session, media_type, tmdb_id, lang):
    url = TMDB_IMAGE_URL.format(media_type=media_type, id=tmdb_id)
    params = {"include_image_language": f"{lang},null"}
    try:
        async with session.get(url, params=params) as res:
            if res.status != 200:
                return None
            data = await res.json()
            backdrops = data.get("backdrops", [])
            if not backdrops:
                return None
            backdrop = backdrops[0]
            return TMDB_POSTER_BASE + backdrop["file_path"]
    except Exception as e:
        log.error(f"TMDb image fetch error: {e}")
        return None

# ----------------------------
# Core Logic
# ----------------------------
async def enrich_programmes(programmes, target_channels, lang):
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(headers={
        "Authorization": f"Bearer {TMDB_API_KEY}",
        "Accept": "application/json"
    }, connector=connector) as session:

        tasks = []
        for prog in programmes:
            channel_id = prog.get("channel")
            if channel_id not in target_channels:
                continue
            title_el = prog.find("title")
            if title_el is None or not title_el.text:
                continue
            title = title_el.text.strip()
            if prog.find("icon") is not None:
                continue
            tasks.append(handle_programme(session, prog, title, lang))

        await asyncio.gather(*tasks)

async def handle_programme(session, prog, title, lang):
    log.info(f"🔍 Searching TMDb for: {title}")
    media_type, tmdb_id = await search_tmdb(session, title)
    if not tmdb_id:
        log.warning(f"❌ No match found for: {title}")
        return

    image_url = await get_landscape(session, media_type, tmdb_id, lang)
    if not image_url:
        log.warning(f"❌ No landscape image found for: {title}")
        return

    log.info(f"✅ Match found for '{title}': {image_url}")
    icon_el = ET.SubElement(prog, "icon")
    icon_el.set("src", image_url)

# ----------------------------
# Main Entrypoint
# ----------------------------
def main():
    args = parse_args()
    if not TMDB_API_KEY:
        log.error("TMDB_API_KEY environment variable not set!")
        return

    log.info("📂 Loading EPG XML...")
    tree = ET.parse(args.input_file)
    root = tree.getroot()

    programmes = root.findall("programme")

    log.info(f"🎯 Enriching {len(programmes)} programmes from selected channels...")
    asyncio.run(enrich_programmes(programmes, args.target_channels, args.language))

    log.info(f"💾 Writing output to: {args.output_file}")
    tree.write(args.output_file, encoding="utf-8", xml_declaration=True)
    log.info("✅ Done.")

# ----------------------------
# Run It
# ----------------------------
if __name__ == "__main__":
    main()