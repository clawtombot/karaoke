"""Stem mixer API routes."""

import logging
import os
from urllib.parse import unquote

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from pikaraoke.constants import STEMS_SUBDIR
from pikaraoke.lib.dependencies import get_karaoke

router = APIRouter(tags=["vocal"])


@router.get("/stem_debug/{msg}")
async def stem_debug(msg: str):
    """Debug endpoint for splash stem mixer logging."""
    logging.info("[STEM-DEBUG] %s", msg)
    return {"ok": True}


@router.get("/stem_toggle/{stem}")
async def stem_toggle(stem: str):
    """Toggle a stem on/off in the mix."""
    k = get_karaoke()
    if not k.vocal_splitter_enabled:
        return JSONResponse({"error": "Stem splitter not enabled"}, status_code=400)
    if not k.toggle_stem(stem):
        return JSONResponse({"error": f"Invalid stem: {stem}"}, status_code=400)
    return {"stem_mix": k.stem_mix}


@router.get("/stem_mix")
async def get_stem_mix():
    """Return current stem mix state."""
    k = get_karaoke()
    return {
        "vocal_splitter_enabled": k.vocal_splitter_enabled,
        "stem_mix": k.stem_mix,
    }


@router.get("/stems/current/{stem}")
async def serve_stem(stem: str):
    """Serve a stem M4A file for the currently playing song.

    URL pattern: /stems/current/{stem}.m4a
    """
    k = get_karaoke()
    now_file = k.playback_controller.now_playing_filename
    if not now_file:
        return JSONResponse({"error": "Nothing playing"}, status_code=404)

    basename = os.path.basename(now_file)
    stems_dir = os.path.join(k.download_path, STEMS_SUBDIR)
    safe_path = os.path.join(stems_dir, basename, stem)

    if not os.path.isfile(safe_path):
        return JSONResponse({"error": "Stem not found"}, status_code=404)

    return FileResponse(safe_path, media_type="audio/mp4")
