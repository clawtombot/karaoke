"""Song queue management routes."""

from __future__ import annotations

import os
from urllib.parse import unquote

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel

from pikaraoke.lib.dependencies import broadcast_event, get_admin_password, get_karaoke
from pikaraoke.routes_fastapi.files import song_metadata

router = APIRouter(tags=["queue"])


# --- Pydantic models ---


class EnqueueBody(BaseModel):
    song: str
    user: str = ""


class ReorderBody(BaseModel):
    old_index: int
    new_index: int


class DownloadErrorDeleteResponse(BaseModel):
    success: bool
    error: str | None = None


# --- Admin helper ---


def is_admin(request: Request) -> bool:
    """Return True if the request carries a valid admin cookie."""
    admin_password = get_admin_password()
    if not admin_password:
        # No password configured — everyone is admin
        return True
    admin_cookie = request.cookies.get("admin_password")
    return admin_cookie == admin_password


# --- Routes ---


@router.get("/get_queue")
async def get_queue():
    """Get the current song queue with metadata."""
    k = get_karaoke()
    queue = k.queue_manager.queue
    for item in queue:
        if "file" in item:
            item["meta"] = song_metadata(k.download_path, item["file"])
    return queue


@router.post("/enqueue")
async def enqueue_post(body: EnqueueBody):
    """Add a song to the queue (JSON body)."""
    return await _do_enqueue(body.song, body.user)


@router.get("/enqueue")
async def enqueue_get(song: str, user: str = ""):
    """Add a song to the queue (query params)."""
    return await _do_enqueue(song, user)


async def _do_enqueue(song: str, user: str) -> dict:
    k = get_karaoke()
    if not os.path.isabs(song):
        song = os.path.join(k.download_path, song)
    rc = k.queue_manager.enqueue(song, user)
    await broadcast_event("queue_update")
    song_title = k.song_manager.filename_from_path(song)
    return {"song": song_title, "success": rc}


@router.get("/queue/edit")
async def queue_edit(request: Request, action: str, song: str = ""):
    """Edit queue items — admin only."""
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    k = get_karaoke()
    success = False
    message = ""

    if action == "clear":
        k.queue_manager.queue_clear()
        message = "Cleared the queue!"
        await broadcast_event("skip", "clear queue")
        success = True
    else:
        song_path = unquote(song)
        song_title = k.song_manager.filename_from_path(song_path)

        success_labels = {
            "top": "Moved to top of queue",
            "bottom": "Moved to bottom of queue",
            "up": "Moved up in queue",
            "down": "Moved down in queue",
            "delete": "Deleted from queue",
        }
        error_labels = {
            "top": "Error moving to top of queue",
            "bottom": "Error moving to bottom of queue",
            "up": "Error moving up in queue",
            "down": "Error moving down in queue",
            "delete": "Error deleting from queue",
        }

        if action == "top":
            success = k.queue_manager.move_to_top(song_path)
        elif action == "bottom":
            success = k.queue_manager.move_to_bottom(song_path)
        else:
            success = k.queue_manager.queue_edit(song_path, action)

        if action in success_labels:
            label = success_labels[action] if success else error_labels[action]
            message = f"{label}: {song_title}"

    return {"success": success, "message": message}


@router.post("/queue/reorder")
async def reorder(request: Request, body: ReorderBody):
    """Reorder queue items — admin only."""
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    k = get_karaoke()
    try:
        success = k.queue_manager.reorder(body.old_index, body.new_index)
        return {"success": success}
    except (ValueError, IndexError):
        return {"success": False}


@router.get("/queue/addrandom/{amount}")
async def add_random(amount: int, request: Request):
    """Add random songs to the queue — admin only."""
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    k = get_karaoke()
    rc = k.queue_manager.queue_add_random(amount)
    await broadcast_event("queue_update")
    if rc:
        return {"success": True, "message": f"Added {amount} random tracks"}
    return {"success": False, "message": "Ran out of songs!"}


@router.get("/queue/downloads")
async def get_current_downloads():
    """Get the status of current and pending downloads."""
    k = get_karaoke()
    return k.download_manager.get_downloads_status()


@router.delete("/queue/downloads/errors/{error_id}")
async def delete_download_error(error_id: str):
    """Remove a download error from the list."""
    k = get_karaoke()
    if k.download_manager.remove_error(error_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Error not found")
