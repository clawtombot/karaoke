"""Video streaming routes for transcoded media playback."""

from __future__ import annotations

import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from pikaraoke.lib.dependencies import get_karaoke
from pikaraoke.lib.file_resolver import FileResolver, get_tmp_dir

router = APIRouter(tags=["stream"])


# --- HLS playlist ---


@router.get("/stream/{id}.m3u8")
async def stream_playlist(id: str):
    """Serve HLS playlist file with no-cache headers."""
    file_path = os.path.join(get_tmp_dir(), f"{id}.m3u8")
    k = get_karaoke()

    # Mark song as started when client connects (idempotent)
    if not k.playback_controller.is_playing:
        now_playing_url = k.playback_controller.now_playing_url
        if now_playing_url and id in now_playing_url:
            k.playback_controller.start_song()

    # Wait up to 5 seconds for the playlist to appear
    max_wait = 50
    wait_count = 0
    while not os.path.exists(file_path) and wait_count < max_wait:
        time.sleep(0.1)
        wait_count += 1

    if not os.path.exists(file_path):
        return Response("Playlist not found", status_code=404)

    with open(file_path, "r") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# --- HLS segments ---


@router.get("/stream/{filename}.m4s")
async def stream_segment_m4s(filename: str):
    """Serve HLS segment file (fragmented MP4)."""
    if ".." in filename or "/" in filename:
        return Response("Invalid segment", status_code=400)

    segment_path = os.path.join(get_tmp_dir(), f"{filename}.m4s")
    if not os.path.exists(segment_path):
        return Response(f"Segment not found: {filename}.m4s", status_code=404)

    return FileResponse(segment_path, media_type="video/mp4")


@router.get("/stream/{filename}_init.mp4")
async def stream_init(filename: str):
    """Serve init.mp4 header file for fragmented MP4 streams."""
    if ".." in filename or "/" in filename:
        return Response("Invalid init file", status_code=400)

    init_path = os.path.join(get_tmp_dir(), f"{filename}_init.mp4")
    if not os.path.exists(init_path):
        return Response("Init file not found", status_code=404)

    return FileResponse(init_path, media_type="video/mp4")


@router.get("/stream/{filename}.ts")
async def stream_segment_ts(filename: str):
    """Serve HLS segment file (legacy MPEG-TS)."""
    if ".." in filename or "/" in filename:
        return Response("Invalid segment", status_code=400)

    segment_path = os.path.join(get_tmp_dir(), f"{filename}.ts")
    if not os.path.exists(segment_path):
        return Response(f"Segment not found: {filename}.ts", status_code=404)

    return FileResponse(segment_path, media_type="video/mp2t")


# --- Progressive MP4 streaming ---


@router.get("/stream/{id}.mp4")
async def stream_progressive_mp4(id: str):
    """Stream progressive MP4 from HLS-generated segments."""
    file_path = os.path.join(get_tmp_dir(), f"{id}.mp4")
    k = get_karaoke()

    # Mark song as started when client connects (idempotent)
    if not k.playback_controller.is_playing:
        now_playing_url = k.playback_controller.now_playing_url
        if now_playing_url and id in now_playing_url:
            k.playback_controller.start_song()

    # Wait up to 5 seconds for the output file
    max_wait = 50
    wait_count = 0
    while not os.path.exists(file_path) and wait_count < max_wait:
        time.sleep(0.1)
        wait_count += 1

    if not os.path.exists(file_path):
        return Response("Stream file not ready", status_code=404)

    def generate():
        position = 0
        chunk_size = 10240 * 1000 * 25  # 25 MB chunks
        with open(file_path, "rb") as file:
            while k.playback_controller.ffmpeg_process.poll() is None:
                file.seek(position)
                chunk = file.read(chunk_size)
                if chunk:
                    yield chunk
                    position += len(chunk)
                time.sleep(1)
            # Yield any remaining data after ffmpeg finishes
            chunk = file.read(chunk_size)
            if chunk:
                yield chunk

    return StreamingResponse(generate(), media_type="video/mp4")


# --- Range-request MP4 (Safari compatible) ---


@router.get("/stream/full/{id}")
async def stream_full(id: str, request: Request):
    """Stream video with range-request support (Safari compatible)."""
    k = get_karaoke()

    # Mark song as started when client connects (idempotent)
    if not k.playback_controller.is_playing:
        now_playing_url = k.playback_controller.now_playing_url
        if now_playing_url and id in now_playing_url:
            k.playback_controller.start_song()

    file_path = os.path.join(get_tmp_dir(), f"{id}.mp4")
    return _stream_file_with_range(file_path, request)


def _stream_file_with_range(file_path: str, request: Request) -> Response:
    """Serve a file with HTTP range-request support."""
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        return Response("File not found.", status_code=404)

    range_header = request.headers.get("Range")
    if not range_header:
        with open(file_path, "rb") as f:
            content = f.read()
        return Response(content, media_type="video/mp4")

    range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return Response("Invalid Range header", status_code=416)

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

    with open(file_path, "rb") as f:
        f.seek(start)
        data = f.read(end - start + 1)

    return Response(
        content=data,
        status_code=206,
        headers={
            "Content-Type": "video/mp4",
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(len(data)),
        },
    )


# --- Background video ---


@router.get("/stream/bg_video")
async def stream_bg_video():
    """Serve the background video file."""
    k = get_karaoke()
    if k.bg_video_path is None:
        return Response("Background video not found.", status_code=404)
    return FileResponse(os.path.abspath(k.bg_video_path), media_type="video/mp4")


# --- Subtitle ---


@router.get("/subtitle/{id}")
async def stream_subtitle(id: str):
    """Serve .ass subtitle file for the current song."""
    k = get_karaoke()
    try:
        original_file_path = k.playback_controller.now_playing_filename
        now_playing_url = k.playback_controller.now_playing_url
        if original_file_path and now_playing_url and id in now_playing_url:
            fr = FileResolver(original_file_path)
            ass_file_path = fr.ass_file_path
            if ass_file_path and os.path.exists(ass_file_path):
                return FileResponse(
                    os.path.abspath(ass_file_path),
                    media_type="text/plain",
                    filename=os.path.basename(ass_file_path),
                )
    except Exception as e:
        k.log_and_send("Failed to stream subtitle: " + str(e), "danger")
        return Response("Subtitle streaming error.", status_code=500)

    return Response("Subtitle file not found for this stream ID.", status_code=404)
