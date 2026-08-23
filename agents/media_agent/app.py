"""
Media agent — wraps the *arr stack (Radarr for films, Sonarr for TV).

Both expose a REST API at /api/v3 with an X-Api-Key header. Set:
    RADARR_URL, RADARR_API_KEY, SONARR_URL, SONARR_API_KEY
Extend the same pattern for Lidarr, Prowlarr, Bazarr, Overseerr, etc.
"""
import os
import httpx

from agentlib import Tool, make_agent_app

RADARR_URL = os.getenv("RADARR_URL", "http://radarr:7878").rstrip("/")
RADARR_KEY = os.getenv("RADARR_API_KEY", "")
SONARR_URL = os.getenv("SONARR_URL", "http://sonarr:8989").rstrip("/")
SONARR_KEY = os.getenv("SONARR_API_KEY", "")


def _get(base, key, path, **params):
    r = httpx.get(f"{base}/api/v3/{path}", headers={"X-Api-Key": key}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(base, key, path, payload):
    r = httpx.post(f"{base}/api/v3/{path}", headers={"X-Api-Key": key}, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def search_movie(term: str) -> str:
    """Search Radarr's indexers for a film by title (not yet added)."""
    hits = _get(RADARR_URL, RADARR_KEY, "movie/lookup", term=term)[:5]
    return "\n".join(f"{m['title']} ({m.get('year','?')}) tmdbId={m.get('tmdbId')}" for m in hits) or "No matches."


def add_movie(tmdb_id: int, quality_profile_id: int = 1, root_folder: str = "/movies") -> str:
    """Add a film to Radarr by TMDB id and start searching for it."""
    look = _get(RADARR_URL, RADARR_KEY, "movie/lookup/tmdb", tmdbId=tmdb_id)
    payload = {**look, "qualityProfileId": quality_profile_id, "rootFolderPath": root_folder,
               "monitored": True, "addOptions": {"searchForMovie": True}}
    added = _post(RADARR_URL, RADARR_KEY, "movie", payload)
    return f"Added '{added['title']}' to Radarr and started the search."


def list_movies() -> str:
    """List films currently in the Radarr library."""
    movies = _get(RADARR_URL, RADARR_KEY, "movie")
    return f"{len(movies)} films in the library. Recent: " + \
        ", ".join(m["title"] for m in movies[-8:]) if movies else "Library is empty."


def add_series(term: str, quality_profile_id: int = 1, root_folder: str = "/tv") -> str:
    """Look up a TV series by title in Sonarr and add it, monitoring all seasons."""
    hits = _get(SONARR_URL, SONARR_KEY, "series/lookup", term=term)
    if not hits:
        return "No series found."
    s = hits[0]
    payload = {**s, "qualityProfileId": quality_profile_id, "rootFolderPath": root_folder,
               "monitored": True, "addOptions": {"searchForMissingEpisodes": True}}
    added = _post(SONARR_URL, SONARR_KEY, "series", payload)
    return f"Added series '{added['title']}' to Sonarr."


TOOLS = [
    Tool(search_movie, {"name": "search_movie", "description": search_movie.__doc__,
         "input_schema": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]}}),
    Tool(add_movie, {"name": "add_movie", "description": add_movie.__doc__,
         "input_schema": {"type": "object", "properties": {
             "tmdb_id": {"type": "integer"}, "quality_profile_id": {"type": "integer"},
             "root_folder": {"type": "string"}}, "required": ["tmdb_id"]}}),
    Tool(list_movies, {"name": "list_movies", "description": list_movies.__doc__,
         "input_schema": {"type": "object", "properties": {}}}),
    Tool(add_series, {"name": "add_series", "description": add_series.__doc__,
         "input_schema": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]}}),
]

ROLE = """You are Wullie's media specialist. You manage a Radarr/Sonarr media
library. Interpret the instruction, call the right tool(s), and reply with a
short plain-English summary of what you did or found. Report errors plainly."""

app = make_agent_app("media", ROLE, TOOLS)
