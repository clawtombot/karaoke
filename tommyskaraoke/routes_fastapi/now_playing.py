"""Now playing status endpoint."""

import logging

from fastapi import APIRouter

from tommyskaraoke.lib.dependencies import get_karaoke

router = APIRouter(tags=["now_playing"])


@router.get("/now_playing")
async def now_playing():
    """Get current playback status."""
    k = get_karaoke()
    try:
        return k.get_now_playing()
    except Exception as e:
        logging.error("Problem loading /now_playing, tommyskaraoke may still be starting up: " + str(e))
        return {}
