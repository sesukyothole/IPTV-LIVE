import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY not found in environment variables")

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

def get_tmdb_data(title):
    if title in MANUAL_ID_OVERRIDES:
        tmdb_type = MANUAL_ID_OVERRIDES[title]['type']
        tmdb_id = MANUAL_ID_OVERRIDES[title]['id']
    else:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=en-US&query={title}"
        response = requests.get(search_url)
        if response.status_code != 200:
            print(f"Search failed for {title}")
            return None
        results = response.json().get("results", [])
        if not results:
            print(f"No results found for {title}")
            return None
        best_match = results[0]
        tmdb_type = best_match.get("media_type", "movie")
        tmdb_id = best_match.get("id")

    details_url = f"https://api.themoviedb.org/3/{tmdb_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
    details = requests.get(details_url).json()

    images_url = f"https://api.themoviedb.org/3/{tmdb_type}/{tmdb_id}/images?api_key={TMDB_API_KEY}&include_image_language=en,null"
    images = requests.get(images_url).json()
    backdrops = images.get("backdrops", [])

    landscape = None
    if backdrops:
        # Choose the highest rated or first backdrop
        backdrop = sorted(backdrops, key=lambda x: x.get("vote_average", 0), reverse=True)[0]
        landscape = f"https://image.tmdb.org/t/p/w780{backdrop['file_path']}"

    return {
        "title": details.get("name") or details.get("title") or title,
        "description": details.get("overview", ""),
        "landscape": landscape
    }

def enrich_epg(epg_path, output_path):
    with open(epg_path, "r", encoding="utf-8") as f:
        epg = json.load(f)

    for program in epg.get("programs", []):
        title = program.get("title")
        if not title:
            continue

        print(f"Enriching: {title}")
        tmdb_data = get_tmdb_data(title)
        if not tmdb_data:
            continue

        program["title"] = tmdb_data["title"]
        program["desc"] = tmdb_data["description"]
        if tmdb_data["landscape"]:
            program["icon"] = tmdb_data["landscape"]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(epg, f, indent=2, ensure_ascii=False)

    print(f"EPG enrichment completed. Output saved to {output_path}")

if __name__ == "__main__":
    enrich_epg("guide.json", "guide_enriched.json")