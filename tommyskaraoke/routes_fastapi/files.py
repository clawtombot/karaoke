"""File management routes for browsing, editing, and deleting songs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tommyskaraoke.constants import STEMS_SUBDIR, stems_complete
from tommyskaraoke.lib.dependencies import get_admin_password, get_karaoke
from tommyskaraoke.lib.metadata_parser import youtube_id_suffix
from tommyskaraoke.lib.pitch.extractor import PITCH_SUBDIR, extract_and_save as extract_pitch
from tommyskaraoke.routes_fastapi.song_config import get_song_config

router = APIRouter(tags=["files"])


def _parse_song_name(filename: str) -> tuple[str, str]:
    """Extract title and artist from filename for lyrics cache lookup."""
    name, _ = os.path.splitext(filename)
    if "---" in name:
        name = name.rsplit("---", 1)[0]
    elif name.endswith("]") and "[" in name:
        bracket_pos = name.rfind("[")
        candidate_id = name[bracket_pos + 1 : -1]
        if len(candidate_id) == 11:
            name = name[:bracket_pos].rstrip()
    # Strip common YouTube tags
    name = re.sub(
        r"\s*[\[\(](?:official|music|lyric|audio|hd|hq|4k|remaster|live|feat\b)[^\]\)]*[\]\)]",
        "", name, flags=re.IGNORECASE,
    ).strip()
    for sep in [" - ", " -- ", " — "]:
        if sep in name:
            parts = name.split(sep, 1)
            return parts[1].strip(), parts[0].strip()
    return name, ""


def song_metadata(download_path: str, song_path: str) -> dict:
    """Check stems, pitch, and lyrics availability for a song."""
    basename = os.path.basename(song_path)
    name_no_ext = os.path.splitext(basename)[0]

    # Stems
    stem_dir = os.path.join(download_path, STEMS_SUBDIR, basename)
    has_stems = os.path.isdir(stem_dir) and stems_complete(stem_dir)

    # Pitch
    pitch_path = os.path.join(download_path, PITCH_SUBDIR, f"{name_no_ext}.json")
    has_pitch = os.path.isfile(pitch_path)

    # Lyrics (check cache via MD5 hash of "title|artist")
    title, artist = _parse_song_name(basename)
    normalized = f"{title}|{artist}".lower().strip()
    h = hashlib.md5(normalized.encode()).hexdigest()
    cache_path = os.path.join(download_path, ".lyrics_cache", f"{h}.json")
    has_lyrics = os.path.isfile(cache_path)
    lyrics_source = None
    lyrics_word_sync = False
    if has_lyrics:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ldata = json.load(f)
            lyrics_source = ldata.get("source", "unknown")
            lyrics_word_sync = ldata.get("has_word_timing", False)
        except Exception:
            pass

    # Per-song config (offsets, noise gate)
    cfg = get_song_config(basename)

    return {
        "stems": has_stems,
        "pitch": has_pitch,
        "lyrics": has_lyrics,
        "lyrics_source": lyrics_source,
        "lyrics_word_sync": lyrics_word_sync,
        "config": cfg,
    }


def _is_admin(request: Request) -> bool:
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


@router.get("/api/browse")
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

    # Include metadata per song (stems, pitch, lyrics availability)
    songs_with_meta = [
        {"path": s, "meta": song_metadata(k.download_path, s)}
        for s in page_songs
    ]

    return {
        "songs": songs_with_meta,
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


# Background pitch backfill task
_backfill_task = None


@router.post("/api/pitch/backfill")
async def pitch_backfill():
    """Trigger pitch extraction for all songs with stems but no pitch data."""
    import asyncio
    import threading

    global _backfill_task
    if _backfill_task and _backfill_task.is_alive():
        return {"ok": False, "message": "Backfill already running"}

    k = get_karaoke()
    dl = k.download_path
    stems_base = os.path.join(dl, STEMS_SUBDIR)
    pitch_dir = os.path.join(dl, PITCH_SUBDIR)

    # Find songs needing pitch extraction
    pending = []
    if os.path.isdir(stems_base):
        for song_dir in os.listdir(stems_base):
            vocals = os.path.join(stems_base, song_dir, "vocals.m4a")
            name_no_ext = os.path.splitext(song_dir)[0]
            done_marker = os.path.join(pitch_dir, f"{name_no_ext}.json.done")
            if os.path.isfile(vocals) and not os.path.exists(done_marker):
                pending.append(song_dir)

    if not pending:
        return {"ok": True, "message": "All songs already have pitch data", "pending": 0}

    def run():
        for song_dir in pending:
            vocals = os.path.join(stems_base, song_dir, "vocals.m4a")
            try:
                extract_pitch(vocals, pitch_dir, output_name=song_dir)
            except Exception as e:
                logging.warning("Pitch backfill failed for %s: %s", song_dir, e)

    _backfill_task = threading.Thread(target=run, daemon=True)
    _backfill_task.start()

    return {"ok": True, "message": f"Backfill started for {len(pending)} songs", "pending": len(pending)}
