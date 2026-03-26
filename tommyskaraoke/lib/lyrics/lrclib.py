"""LRCLIB REST API client for fetching synced lyrics.

API docs: https://lrclib.net/docs
"""

import logging

import httpx

from tommyskaraoke.lib.lyrics.lrc_parser import parse_lrc
from tommyskaraoke.lib.lyrics.models import SongLyrics

LRCLIB_BASE = "https://lrclib.net/api"
REQUEST_TIMEOUT = 10.0
USER_AGENT = "TommysKaraoke/1.0 (https://github.com/tomm3hgunn/TommysKaraoke)"


async def search_lyrics(title: str, artist: str) -> SongLyrics | None:
    """Search LRCLIB for synced lyrics by track and artist name.

    Tries the exact-match ``/get`` endpoint first, then falls back to
    ``/search`` for a fuzzy match.

    Args:
        title: Song title.
        artist: Artist name.

    Returns:
        SongLyrics with parsed LRC lines, or None if nothing found.
    """
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers) as client:
        # Try exact match first
        result = await _try_get(client, title, artist)
        if result is not None:
            return result

        # Fall back to search
        return await _try_search(client, title, artist)


async def _try_get(client: httpx.AsyncClient, title: str, artist: str) -> SongLyrics | None:
    """Try the exact-match /get endpoint."""
    try:
        resp = await client.get(
            f"{LRCLIB_BASE}/get",
            params={"track_name": title, "artist_name": artist},
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        return _parse_response(data)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logging.warning("LRCLIB /get failed: %s", e)
        return None


async def _try_search(client: httpx.AsyncClient, title: str, artist: str) -> SongLyrics | None:
    """Fall back to the /search endpoint for fuzzy matching."""
    try:
        query = f"{artist} {title}".strip()
        resp = await client.get(
            f"{LRCLIB_BASE}/search",
            params={"q": query},
        )
        if resp.status_code != 200:
            return None

        results = resp.json()
        if not isinstance(results, list) or not results:
            return None

        # Pick the first result with synced lyrics
        for item in results:
            parsed = _parse_response(item)
            if parsed is not None:
                return parsed

        return None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logging.warning("LRCLIB /search failed: %s", e)
        return None


def _parse_response(data: dict) -> SongLyrics | None:
    """Parse a LRCLIB response object into SongLyrics."""
    synced = data.get("syncedLyrics")
    if not synced:
        return None

    lines = parse_lrc(synced)
    if not lines:
        return None

    has_word_timing = any(line.words for line in lines)

    return SongLyrics(
        source="lrclib",
        language="",
        lines=lines,
        has_word_timing=has_word_timing,
    )
