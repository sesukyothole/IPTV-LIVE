import asyncio
import httpx
import os

TMDB_API_KEY = os.environ["TMDB_API_KEY"]

TARGET_CHANNEL_IDS = [
    403788, 403674, 403837, 403794, 403620,
    403772, 403655, 403847, 403576
]

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

async def fetch_tmdb_poster(client, title, override=None):
    try:
        if override:
            tmdb_type = override["type"]
            tmdb_id = override["id"]
            url = f"https://api.themoviedb.org/3/{tmdb_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
        else:
            url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=en-US&query={title}"

        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        result = data if override else data["results"][0] if data["results"] else None
        if not result:
            return title, None

        backdrop_path = result.get("backdrop_path")
        poster_path = result.get("poster_path")
        if backdrop_path:
            return title, f"https://image.tmdb.org/t/p/w780{backdrop_path}"
        elif poster_path and result.get("poster_path_width", 0) > result.get("poster_path_height", 0):
            return title, f"https://image.tmdb.org/t/p/w780{poster_path}"
        return title, None
    except Exception as e:
        return title, None

async def main():
    titles = list(MANUAL_ID_OVERRIDES.keys())
    async with httpx.AsyncClient() as client:
        tasks = []
        for title in titles:
            override = MANUAL_ID_OVERRIDES.get(title)
            tasks.append(fetch_tmdb_poster(client, title, override))

        results = await asyncio.gather(*tasks)

    for title, url in results:
        if url:
            print(f"{title}: {url}")
        else:
            print(f"{title}: No landscape poster found")

if __name__ == "__main__":
    asyncio.run(main())