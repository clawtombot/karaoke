"""Background music streaming routes."""

from __future__ import annotations

import os
import random
import urllib.parse

from fastapi import APIRouter
from fastapi.responses import FileResponse

from tommyskaraoke.lib.dependencies import get_karaoke

router = APIRouter(tags=["background_music"])


def _create_randomized_playlist(input_directory: str, base_url: str, max_songs: int = 50) -> list[str]:
    files = [
        f
        for f in os.listdir(input_directory)
        if f.lower().endswith(".mp3") or f.lower().endswith(".mp4")
    ]
    random.shuffle(files)
    files = files[:max_songs]
    playlist = []
    for f in files:
        encoded = urllib.parse.quote(f.encode("utf8"))
        playlist.append(f"{base_url}/{encoded}")
    return playlist


@router.get("/bg_music/{file}")
async def bg_music(file: str):
    """Stream a background music file."""
    k = get_karaoke()
    mp3_path = os.path.abspath(os.path.join(k.bg_music_path, file))
    return FileResponse(mp3_path, media_type="audio/mpeg")


@router.get("/bg_playlist")
async def bg_playlist():
    """Get a randomized background music playlist."""
    k = get_karaoke()
    if k.bg_music_path is None or not os.path.exists(k.bg_music_path):
        return []
    return _create_randomized_playlist(k.bg_music_path, "/bg_music", 50)
