"""YouTube search and download routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pikaraoke.lib.dependencies import get_karaoke
from pikaraoke.lib.youtube_dl import get_search_results, get_stream_url

router = APIRouter(tags=["search"])


# --- Pydantic models ---


class DownloadBody(BaseModel):
    song_url: str
    song_added_by: str
    song_title: str
    queue: bool = False


# --- Routes ---


@router.get("/autocomplete")
async def autocomplete(q: str):
    """Search available songs for autocomplete."""
    k = get_karaoke()
    q_lower = q.lower()
    result = []
    for each in k.song_manager.songs:
        if q_lower in each.lower():
            result.append(
                {
                    "path": each,
                    "fileName": k.song_manager.filename_from_path(each),
                    "type": "autocomplete",
                }
            )
    return result


@router.get("/preview")
async def preview(url: str):
    """Get a direct stream URL for previewing a YouTube video."""
    stream_url = get_stream_url(url)
    if stream_url is None:
        raise HTTPException(status_code=500, detail="Could not fetch stream URL")
    return {"stream_url": stream_url}


@router.post("/download")
async def download(body: DownloadBody):
    """Queue a YouTube video for download."""
    k = get_karaoke()
    k.download_manager.queue_download(body.song_url, body.queue, body.song_added_by, body.song_title)
    return {"status": "ok"}
