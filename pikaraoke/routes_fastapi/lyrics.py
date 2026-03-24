"""Lyrics API routes for fetching timed lyrics."""

import logging
import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from pikaraoke.lib.dependencies import get_karaoke
from pikaraoke.lib.lyrics import LyricsManager

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
