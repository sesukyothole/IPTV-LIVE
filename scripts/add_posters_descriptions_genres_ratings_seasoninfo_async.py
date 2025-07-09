import sys
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime

TMDB_API_KEY = None
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"  # Portrait size
TARGET_CHANNELS = {
    "403788", "493674", "403837", "403794", "403620",
    "403655", "8359", "403847", "403461", "403576"
}

# Cache genre mappings globally for movies and TV shows
MOVIE_GENRES = {}
TV_GENRES = {}

async def fetch_json(session, url, params):
    async with session.get(url, params=params) as response:
        response.raise_for_status()
        return await response.json()

async def load_genres(session):
    global MOVIE_GENRES, TV_GENRES
    movie_data = await fetch_json(session, f"{TMDB_BASE}/genre/movie/list", {"api_key": TMDB_API_KEY})
    tv_data = await fetch_json(session, f"{TMDB_BASE}/genre/tv/list", {"api_key": TMDB_API_KEY})
    MOVIE_GENRES = {g["id"]: g["name"] for g in movie_data.get("genres", [])}
    TV_GENRES = {g["id"]: g["name"] for g in tv_data.get("genres", [])}

async def search_tmdb(session, title):
    params = {"api_key": TMDB_API_KEY, "query": title, "include_adult": "false"}
    # Search Movie first
    movie_results = await fetch_json(session, f"{TMDB_BASE}/search/movie", params)
    if movie_results.get("results"):
        movie = movie_results["results"][0]
        return "movie", movie

    # If no movie found, search TV
    tv_results = await fetch_json(session, f"{TMDB_BASE}/search/tv", params)
    if tv_results.get("results"):
        tv = tv_results["results"][0]
        return "tv", tv

    return None, None

def map_genres(genre_ids, content_type):
    if content_type == "movie":
        return [MOVIE_GENRES.get(gid, str(gid)) for gid in genre_ids]
    else:
        return [TV_GENRES.get(gid, str(gid)) for gid in genre_ids]

def get_mpaa_rating(releases, content_type):
    # For movies: check releases['results'] for US MPAA rating
    # For TV shows: check content_ratings['results']
    if content_type == "movie":
        for release in releases.get("results", []):
            if release.get("iso_3166_1") == "US":
                rating = release.get("certification", "").strip()
                if rating:
                    return rating
    elif content_type == "tv":
        for rating in releases.get("results", []):
            if rating.get("iso_3166_1") == "US":
                rating_value = rating.get("rating", "").strip()
                if rating_value:
                    return rating_value
    return None

async def enrich_programme(session, programme):
    title_el = programme.find("title")
    channel = programme.get("channel", "")
    if title_el is None or channel not in TARGET_CHANNELS:
        return

    title = title_el.text or ""
    print(f"🔍 Searching TMDb for '{title}'...")

    content_type, data = await search_tmdb(session, title)
    if not data:
        print(f"❌ No TMDb data found for '{title}'")
        return

    # Poster
    poster_path = data.get("poster_path")
    if poster_path:
        poster_url = TMDB_IMAGE_BASE + poster_path
        icon_el = programme.find("icon")
        if icon_el is None:
            icon_el = ET.SubElement(programme, "icon")
        icon_el.set("src", poster_url)
        print(f"✅ Poster added for '{title}'")
    else:
        print(f"⚠️ Poster not found for '{title}'")

    # Description
    desc_text = data.get("overview", "").strip()
    if desc_text:
        desc_el = programme.find("desc")
        if desc_el is None:
            desc_el = ET.SubElement(programme, "desc")
        desc_el.text = desc_text
        print(f"✅ Description added for '{title}'")
    else:
        print(f"⚠️ Description not found for '{title}'")

    # Genres
    genre_ids = data.get("genre_ids") or []
    # Sometimes full genres list is in 'genres' key with name & id
    if not genre_ids and "genres" in data:
        genre_ids = [g.get("id") for g in data["genres"] if g.get("id") is not None]

    genres = map_genres(genre_ids, content_type)
    if genres:
        genre_text = " / ".join(genres)
        # Remove existing genre elements
        for old_genre in programme.findall("category"):
            programme.remove(old_genre)
        # Add genres as <category> tags (Kodi reads these)
        for g in genres:
            cat_el = ET.SubElement(programme, "category")
            cat_el.text = g
        print(f"✅ Genres added for '{title}': {genre_text}")
    else:
        print(f"⚠️ Genres not found for '{title}'")

    # MPAA Rating
    rating = None
    if content_type == "movie":
        releases = await fetch_json(session, f"{TMDB_BASE}/movie/{data['id']}/release_dates", {"api_key": TMDB_API_KEY})
        rating = get_mpaa_rating(releases, "movie")
    elif content_type == "tv":
        ratings = await fetch_json(session, f"{TMDB_BASE}/tv/{data['id']}/content_ratings", {"api_key": TMDB_API_KEY})
        rating = get_mpaa_rating(ratings, "tv")

    if rating:
        rating_el = programme.find("rating[@system='MPAA']")
        if rating_el is None:
            rating_el = ET.SubElement(programme, "rating", attrib={"system": "MPAA"})
        value_el = rating_el.find("value")
        if value_el is None:
            value_el = ET.SubElement(rating_el, "value")
        value_el.text = rating
        print(f"✅ MPAA Rating '{rating}' added for '{title}'")
    else:
        print(f"⚠️ No MPAA Rating found for '{title}'")

    # Season/Episode info (if TV show)
    if content_type == "tv":
        season_number = data.get("season_number")
        episode_number = data.get("episode_number")

        # If season or episode number missing, try to parse from episode title or skip
        ep_num_el = programme.find("episode-num[@system='xmltv_ns']")
        if ep_num_el is not None:
            # xmltv_ns format: season and episode zero-based, e.g. 0.25 = S1E26
            try:
                s, e = ep_num_el.text.split(".")
                season_number = int(s) + 1
                episode_number = int(e) + 1
            except Exception:
                pass

        if season_number and episode_number:
            se_text = f"S{season_number}E{episode_number}"
            se_el = programme.find("episode-num[@system='onscreen']")
            if se_el is None:
                se_el = ET.SubElement(programme, "episode-num", attrib={"system": "onscreen"})
            se_el.text = se_text
            print(f"✅ Season/Episode info '{se_text}' added for '{title}'")

async def enrich_epg(input_path, output_path):
    global TMDB_API_KEY
    TMDB_API_KEY = sys.argv[3] if len(sys.argv) > 3 else None
    if not TMDB_API_KEY:
        print("❌ TMDB_API_KEY is required as third argument or environment variable.")
        return

    tree = ET.parse(input_path)
    root = tree.getroot()

    async with aiohttp.ClientSession() as session:
        await load_genres(session)
        tasks = []
        for programme in root.findall("programme"):
            tasks.append(enrich_programme(session, programme))
        await asyncio.gather(*tasks)

    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"🎉 EPG enriched and saved to '{output_path}'")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_posters_descriptions_genres_ratings_seasoninfo_async.py input_epg.xml output_epg.xml [TMDB_API_KEY]")
    else:
        asyncio.run(enrich_epg(sys.argv[1], sys.argv[2]))
