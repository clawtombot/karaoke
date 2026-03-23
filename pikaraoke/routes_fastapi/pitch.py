"""Pitch data API routes."""

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from pikaraoke.lib.dependencies import get_karaoke
from pikaraoke.lib.pitch.extractor import PITCH_SUBDIR, get_pitch_data

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
