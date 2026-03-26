"""Pitch data API routes."""

import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from tommyskaraoke.constants import STEMS_SUBDIR
from tommyskaraoke.lib.dependencies import get_karaoke
from tommyskaraoke.lib.pitch.extractor import PITCH_SUBDIR, get_pitch_data

router = APIRouter(tags=["pitch"])


@router.get("/api/pitch/{stream_uid}")
async def get_pitch(stream_uid: str):
    """Get precomputed pitch data for the currently playing song."""
    k = get_karaoke()
    now_file = k.playback_controller.now_playing_filename
    if not now_file:
        return JSONResponse({"error": "No song playing"}, status_code=404)

    # Check if this stream_uid matches current song
    now_url = k.playback_controller.now_playing_url
    if not now_url or stream_uid not in now_url:
        return JSONResponse({"error": "Stream ID mismatch"}, status_code=404)

    basename = os.path.basename(now_file)
    data = get_pitch_data(k.download_path, basename)
    if data is None:
        return JSONResponse({"error": "Pitch data not available"}, status_code=404)

    return data


@router.get("/api/pitch_backing/{stream_uid}")
async def get_pitch_backing(stream_uid: str):
    """Get precomputed pitch data for the backing vocals of the currently playing song."""
    k = get_karaoke()
    now_file = k.playback_controller.now_playing_filename
    if not now_file:
        return JSONResponse({"error": "No song playing"}, status_code=404)

    now_url = k.playback_controller.now_playing_url
    if not now_url or stream_uid not in now_url:
        return JSONResponse({"error": "Stream ID mismatch"}, status_code=404)

    basename = os.path.basename(now_file)
    name_base = os.path.splitext(basename)[0]
    data = get_pitch_data(k.download_path, f"{name_base}_backing")
    if data is None:
        return JSONResponse({"error": "Backing pitch data not available"}, status_code=404)

    return data


@router.get("/api/singer/{stream_uid}")
async def get_singer_info(stream_uid: str):
    """Get singer gender classification for the currently playing song.

    Returns: {"lead": "male"|"female", "backing": "male"|"female"}
    Colors: male=blue, female=pink, overlap=purple
    """
    k = get_karaoke()
    now_file = k.playback_controller.now_playing_filename
    if not now_file:
        return JSONResponse({"error": "No song playing"}, status_code=404)

    now_url = k.playback_controller.now_playing_url
    if not now_url or stream_uid not in now_url:
        return JSONResponse({"error": "Stream ID mismatch"}, status_code=404)

    basename = os.path.basename(now_file)
    singer_path = os.path.join(k.download_path, STEMS_SUBDIR, basename, "singer.json")
    if not os.path.isfile(singer_path):
        return JSONResponse({"error": "Singer data not available"}, status_code=404)

    with open(singer_path) as f:
        return json.load(f)
