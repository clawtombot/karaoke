"""Playback control routes for skip, pause, volume, and transpose."""

from fastapi import APIRouter

from pikaraoke.lib.dependencies import broadcast_event, get_karaoke

router = APIRouter(tags=["controller"])


@router.get("/skip")
async def skip():
    """Skip the currently playing song."""
    k = get_karaoke()
    await broadcast_event("skip", "user command")
    k.playback_controller.skip()
    return {"ok": True}


@router.get("/pause")
async def pause():
    """Toggle pause/resume playback."""
    k = get_karaoke()
    if k.playback_controller.is_paused:
        await broadcast_event("play")
    else:
        await broadcast_event("pause")
    k.playback_controller.pause()
    return {"ok": True}


@router.get("/transpose/{semitones}")
async def transpose(semitones: int):
    """Transpose (pitch shift) the current song."""
    k = get_karaoke()
    await broadcast_event("skip", "transpose current")
    k.transpose_current(semitones)
    return {"ok": True}


@router.get("/restart")
async def restart():
    """Restart the current song from the beginning."""
    k = get_karaoke()
    await broadcast_event("restart")
    k.restart()
    return {"ok": True}


@router.get("/volume/{volume}")
async def volume(volume: float):
    """Set the playback volume."""
    k = get_karaoke()
    await broadcast_event("volume", volume)
    k.volume_change(volume)
    return {"ok": True}


@router.get("/vol_up")
async def vol_up():
    """Increase volume by 10%."""
    k = get_karaoke()
    await broadcast_event("volume", "up")
    k.vol_up()
    return {"ok": True}


@router.get("/vol_down")
async def vol_down():
    """Decrease volume by 10%."""
    k = get_karaoke()
    await broadcast_event("volume", "down")
    k.vol_down()
    return {"ok": True}


@router.get("/seek/{position}")
async def seek(position: float):
    """Seek to a position in seconds."""
    k = get_karaoke()
    await broadcast_event("seek", position)
    k.playback_controller.now_playing_position = position
    return {"ok": True}
