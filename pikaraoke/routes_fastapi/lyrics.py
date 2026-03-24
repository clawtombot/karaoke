"""Lyrics API routes for fetching timed lyrics."""

import logging
import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pikaraoke.lib.dependencies import get_karaoke, get_sio
from pikaraoke.lib.lyrics import LyricsManager
from pikaraoke.lib.lyrics.cache import LyricsCache

router = APIRouter(tags=["lyrics"])

# Module-level singleton, initialized on first request
_lyrics_manager: LyricsManager | None = None


def _get_manager() -> LyricsManager:
    """Get or create the LyricsManager singleton."""
    global _lyrics_manager
    if _lyrics_manager is None:
        k = get_karaoke()
        cache_dir = os.path.join(k.download_path, ".lyrics_cache")
        _lyrics_manager = LyricsManager(cache_dir=cache_dir, download_path=k.download_path)
    return _lyrics_manager


# NOTE: /search must be defined BEFORE /{stream_uid} so FastAPI doesn't
# match "search" as a stream_uid path parameter.

@router.get("/api/lyrics/search")
async def search_lyrics(
    title: str = Query(..., description="Song title"),
    artist: str = Query("", description="Artist name"),
):
    """Search for lyrics by title and artist."""
    manager = _get_manager()

    lyrics = await manager.get_lyrics(title=title, artist=artist)
    if lyrics is None:
        return JSONResponse({"error": "No lyrics found"}, status_code=404)

    return lyrics.to_dict()


@router.get("/api/lyrics/candidates")
async def lyrics_candidates(
    title: str = Query(...),
    artist: str = Query(""),
):
    """Search multiple sources and return a list of lyrics candidates."""
    import httpx
    from pikaraoke.lib.lyrics import lrclib, netease
    from pikaraoke.lib.lyrics.lrc_parser import parse_lrc

    results = []
    query = f"{artist} {title}".strip()

    # NetEase: get multiple song IDs
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{netease.NETEASE_BASE}/search/get",
                params={"s": query, "type": 1, "limit": 8},
                headers={"User-Agent": netease.USER_AGENT, "Referer": "https://music.163.com/"},
            )
            if resp.status_code == 200:
                songs = resp.json().get("result", {}).get("songs", [])
                for song in songs[:5]:
                    song_id = song.get("id")
                    name = song.get("name", "")
                    artists = ", ".join(a.get("name", "") for a in song.get("artists", []))
                    results.append({
                        "id": f"netease:{song_id}",
                        "title": name,
                        "artist": artists,
                        "source": "netease",
                    })
    except Exception as e:
        logging.warning("NetEase candidate search failed: %s", e)

    # LRCLIB: get multiple results
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": lrclib.USER_AGENT}) as client:
            resp = await client.get(f"{lrclib.LRCLIB_BASE}/search", params={"q": query})
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    for item in items[:5]:
                        if not item.get("syncedLyrics"):
                            continue
                        results.append({
                            "id": f"lrclib:{item.get('id', '')}",
                            "title": item.get("trackName", ""),
                            "artist": item.get("artistName", ""),
                            "source": "lrclib",
                            "album": item.get("albumName", ""),
                            "duration": item.get("duration", 0),
                        })
    except Exception as e:
        logging.warning("LRCLIB candidate search failed: %s", e)

    return {"candidates": results}


class SelectLyricsBody(BaseModel):
    candidate_id: str  # "netease:12345" or "lrclib:67890"
    title: str = ""  # Override title for cache key (optional)
    artist: str = ""  # Override artist for cache key (optional)


@router.post("/api/lyrics/select")
async def select_lyrics(body: SelectLyricsBody):
    """Fetch lyrics for a specific candidate and save to cache for the current song."""
    k = get_karaoke()
    now_file = k.playback_controller.now_playing_filename

    # Determine cache key: use overrides if given, else parse from now_playing
    if body.title:
        title, artist = body.title, body.artist
    elif now_file:
        title, artist = _parse_filename(os.path.basename(now_file))
    else:
        return JSONResponse({"error": "No song playing and no title provided"}, status_code=404)

    source, sid = body.candidate_id.split(":", 1)
    lyrics = None

    if source == "netease":
        from pikaraoke.lib.lyrics import netease
        lyrics = await netease.get_lyrics(int(sid))
    elif source == "lrclib":
        import httpx
        from pikaraoke.lib.lyrics import lrclib
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": lrclib.USER_AGENT}) as client:
            resp = await client.get(f"{lrclib.LRCLIB_BASE}/get/{sid}")
            if resp.status_code == 200:
                lyrics = lrclib._parse_response(resp.json())

    if lyrics is None:
        return JSONResponse({"error": "Failed to fetch lyrics for candidate"}, status_code=404)

    # Only estimate word timing if the source has partial word data (YRC mix).
    # Pure line-synced sources (lrclib, netease LRC) stay line-level.

    # Save to cache under song's key
    cache_dir = os.path.join(k.download_path, ".lyrics_cache")
    cache = LyricsCache(cache_dir)
    cache.put(title, artist, lyrics)

    # Notify splash to reload
    sio = get_sio()
    await sio.emit("lyrics_reload")

    return lyrics.to_dict()


@router.get("/api/lyrics/{stream_uid}")
async def get_lyrics_for_stream(stream_uid: str):
    """Get lyrics for the currently playing song by stream UID.

    Resolves the stream UID to the playing song's metadata and fetches
    timed lyrics from available sources.
    """
    k = get_karaoke()
    manager = _get_manager()

    # Verify this stream UID matches the currently playing song
    now_playing_url = k.playback_controller.now_playing_url
    if not now_playing_url or stream_uid not in now_playing_url:
        return JSONResponse({"error": "No matching song playing"}, status_code=404)

    file_path = k.playback_controller.now_playing_filename
    if not file_path:
        return JSONResponse({"error": "No song currently playing"}, status_code=404)

    # Extract title and artist from filename
    title, artist = _parse_filename(os.path.basename(file_path))

    lyrics = await manager.get_lyrics(title=title, artist=artist, file_path=file_path)
    if lyrics is None:
        return JSONResponse({"error": "No lyrics found"}, status_code=404)

    return lyrics.to_dict()


def _parse_filename(filename: str) -> tuple[str, str]:
    """Extract title and artist from a song filename.

    Handles PiKaraoke format (Title---ID.mp4) and yt-dlp format (Title [ID].mp4).
    Attempts to split on common separators like " - " for artist/title.
    """
    # Strip extension
    name, _ = os.path.splitext(filename)

    # Remove video ID: PiKaraoke "---XXXXXXXXXXX" or yt-dlp " [XXXXXXXXXXX]"
    if "---" in name:
        name = name.rsplit("---", 1)[0]
    elif name.endswith("]") and "[" in name:
        bracket_pos = name.rfind("[")
        candidate_id = name[bracket_pos + 1 : -1]
        if len(candidate_id) == 11:
            name = name[:bracket_pos].rstrip()

    # Try to split artist - title
    for sep in [" - ", " -- ", " — "]:
        if sep in name:
            parts = name.split(sep, 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            return _clean_title(title), artist

    return _clean_title(name.strip()), ""


def _clean_title(title: str) -> str:
    """Strip common YouTube suffixes that pollute lyrics searches."""
    import re

    # Remove bracketed/parenthesized tags: [OFFICIAL VIDEO], (Official Music Video), etc.
    title = re.sub(
        r"\s*[\[\(](?:official|music|lyric|audio|hd|hq|4k|remaster|live|feat\b)[^\]\)]*[\]\)]",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip()
