import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
import sys

OMDB_API_KEY = os.getenv("OMDB_API_KEY") or (len(sys.argv) > 3 and sys.argv[3])
if not OMDB_API_KEY:
    print("❌ OMDB_API_KEY is required as third argument or environment variable.")
    sys.exit(1)

OMDB_BASE = "http://www.omdbapi.com/"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

def extract_program_year(programme):
    date_el = programme.find("date")
    if date_el is not None and date_el.text and len(date_el.text) >= 4:
        return date_el.text[:4]
    start = programme.get("start")
    if start and len(start) >= 4:
        return start[:4]
    return None

async def fetch_imdb_id(session, title, year=None):
    params = {"apikey": OMDB_API_KEY, "t": title}
    if year:
        params["y"] = year
    async with session.get(OMDB_BASE, params=params) as response:
        data = await response.json()
        if data.get("Response") == "True":
            return data.get("imdbID")
    return None

def already_has_imdb(programme):
    return any(e.attrib.get("system") == "imdb" for e in programme.findall("episode-num"))

async def process_programme(session, programme):
    channel = programme.attrib.get("channel")
    if channel not in TARGET_CHANNELS:
        return

    if already_has_imdb(programme):
        return

    title_el = programme.find("title")
    if title_el is None:
        return

    title = title_el.text.strip()
    year = extract_program_year(programme)

    print(f"🔍 Searching IMDb for: {title} ({year or 'unknown'})")

    try:
        imdb_id = await fetch_imdb_id(session, title, year)
        if imdb_id:
            epnum = ET.SubElement(programme, "episode-num")
            epnum.set("system", "imdb")
            epnum.text = imdb_id
            print(f"✅ IMDb ID found: {imdb_id}")
        else:
            print(f"❌ No IMDb match for: {title}")
    except Exception as e:
        print(f"❌ Error processing {title}: {e}")

async def enrich_with_imdb_ids(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()
    programmes = root.findall("programme")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(process_programme(session, p) for p in programmes))

    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n🎬 IMDb IDs added to: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 add_imdb_ids_async.py epg.xml epg_with_imdb.xml [OMDB_API_KEY]")
        sys.exit(1)

    asyncio.run(enrich_with_imdb_ids(sys.argv[1], sys.argv[2]))
