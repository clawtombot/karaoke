"""File management routes for browsing, editing, and deleting songs."""

from __future__ import annotations

import logging
import os
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pikaraoke.lib.dependencies import get_admin_password, get_karaoke
from pikaraoke.lib.metadata_parser import youtube_id_suffix

router = APIRouter(tags=["files"])


def _is_admin(request: Request) -> bool:
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


@router.get("/browse")
async def browse(
    request: Request,
    page: int = 1,
    letter: str | None = None,
    sort: str | None = None,
):
    """Browse available songs, paginated."""
    k = get_karaoke()
    available_songs = k.song_manager.songs

    if letter:
        result = []
        if letter == "numeric":
            for song in available_songs:
                f = k.song_manager.filename_from_path(song)[0]
                if f.isnumeric():
                    result.append(song)
        else:
            for song in available_songs:
                f = k.song_manager.filename_from_path(song).lower()
                normalized = unicodedata.normalize("NFD", f)
                base_char = normalized[0] if normalized else ""
                if base_char == letter.lower():
                    result.append(song)
        available_songs = result

    if sort == "date":
        songs = sorted(available_songs, key=lambda x: os.path.getmtime(x), reverse=True)
    else:
        songs = available_songs

    per_page = k.browse_results_per_page
    total = len(songs)
    start_index = (page - 1) * per_page
    page_songs = songs[start_index : start_index + per_page]

    return {
        "songs": page_songs,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/files/delete")
async def delete_file(request: Request, song: str):
    """Delete a song file."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    if k.queue_manager.is_song_in_queue(song):
        return JSONResponse(
            {
                "ok": False,
                "error": f"Can't delete this song because it is in the current queue: {song}",
            },
            status_code=409,
        )
    k.song_manager.delete(song)
    filename = k.song_manager.filename_from_path(song)
    return {"ok": True, "message": f"Song deleted: {filename}"}


@router.get("/files/edit")
async def edit_file(request: Request, song: str):
    """Get song info for renaming."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    if k.queue_manager.is_song_in_queue(song):
        return JSONResponse(
            {
                "ok": False,
                "error": f"Can't edit this song because it is in the current queue: {song}",
            },
            status_code=409,
        )
    raw_stem = k.song_manager.filename_from_path(song, tidy=False)
    return {"ok": True, "song": song, "raw_stem": raw_stem}


class RenameBody(BaseModel):
    new_file_name: str
    old_file_name: str


@router.post("/files/edit")
async def rename_file(request: Request, body: RenameBody):
    """Rename a song file."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    old_name = body.old_file_name
    new_name = body.new_file_name

    if k.queue_manager.is_song_in_queue(old_name):
        return JSONResponse(
            {
                "ok": False,
                "error": f"Can't edit this song because it is in the current queue: {old_name}",
            },
            status_code=409,
        )

    yt_suffix = youtube_id_suffix(old_name)
    new_name_full = new_name + yt_suffix
    file_extension = os.path.splitext(old_name)[1]

    if os.path.isfile(os.path.join(k.song_manager.download_path, new_name_full + file_extension)):
        return JSONResponse(
            {
                "ok": False,
                "error": f"Error renaming file: '{old_name}' to '{new_name_full + file_extension}', Filename already exists",
            },
            status_code=409,
        )

    try:
        k.song_manager.rename(old_name, new_name_full)
    except OSError as e:
        logging.error(f"Error renaming file: {e}")
        return JSONResponse(
            {"ok": False, "error": f"Error renaming file: '{old_name}' to '{new_name_full}', {e}"},
            status_code=500,
        )

    return {"ok": True, "message": f"Renamed file: {old_name} to {new_name_full}"}
