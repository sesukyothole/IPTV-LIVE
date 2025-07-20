import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import logging
from datetime import datetime
from tqdm import tqdm
import xmltodict

EPG_URL = "https://epg.pw/xmltv/epg_US.xml"
OUTPUT_EPG = "epg.xml"

TARGET_CHANNELS = {
    "403788", "403674", "403837", "403794", "403620",
    "403655", "403847", "403772", "403576", "403926",
    "403461"
}

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def fetch_tmdb_data(session, name):
    if name in MANUAL_ID_OVERRIDES:
        media = MANUAL_ID_OVERRIDES[name]
        tmdb_url = f"https://api.themoviedb.org/3/{media['type']}/{media['id']}?api_key=${{TMDB_API_KEY}}&language=en-US"
        async with session.get(tmdb_url) as resp:
            return await resp.json()
    return None

async def enrich_program(program, session):
    title = program.get('title', {}).get('#text')
    if not title:
        return
    tmdb_data = await fetch_tmdb_data(session, title)
    if tmdb_data:
        if 'overview' in tmdb_data:
            program['desc'] = {'@lang': 'en', '#text': tmdb_data['overview']}
        if 'genres' in tmdb_data:
            program['category'] = [{'@lang': 'en', '#text': g['name']} for g in tmdb_data['genres']]
        if 'first_air_date' in tmdb_data or 'release_date' in tmdb_data:
            date = tmdb_data.get('first_air_date') or tmdb_data.get('release_date')
            program['date'] = date.split('-')[0]
        if 'poster_path' in tmdb_data:
            program['icon'] = {
                '@src': f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}",
                '@type': 'landscape'
            }
        if 'content_ratings' in tmdb_data and 'results' in tmdb_data['content_ratings']:
            for rating in tmdb_data['content_ratings']['results']:
                if rating['iso_3166_1'] == 'US':
                    program['rating'] = {'@system': 'MPAA', 'value': rating['rating']}
                    break

async def main():
    logging.info("Fetching EPG XML...")
    async with aiohttp.ClientSession() as session:
        async with session.get(EPG_URL) as resp:
            epg_xml = await resp.text()

    logging.info("Parsing EPG...")
    epg_dict = xmltodict.parse(epg_xml)
    programmes = epg_dict['tv']['programme']

    logging.info("Enriching programmes...")
    enriched = 0
    async with aiohttp.ClientSession() as session:
        for prog in tqdm(programmes):
            if prog['@channel'] in TARGET_CHANNELS:
                await enrich_program(prog, session)
                enriched += 1

    logging.info(f"Enriched {enriched} programmes. Writing output to {OUTPUT_EPG}...")
    with open(OUTPUT_EPG, 'w', encoding='utf-8') as f:
        f.write(xmltodict.unparse(epg_dict, pretty=True))

    logging.info("Done.")

if __name__ == '__main__':
    asyncio.run(main())
