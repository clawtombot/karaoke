"""FastAPI application entry point — replaces Flask app.py.

Serves the Svelte SPA, JSON API routes, and Socket.IO via python-socketio ASGI.
No gevent monkey-patching. Native async/await throughout.
"""

import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pikaraoke import VERSION
from pikaraoke.lib.args import parse_pikaraoke_args
from pikaraoke.lib.dependencies import configure as configure_deps
from pikaraoke.lib.ffmpeg import is_ffmpeg_installed
from pikaraoke.lib.file_resolver import delete_tmp_dir
from pikaraoke.lib.get_platform import get_platform, has_js_runtime
from pikaraoke.lib.song_manager import SongManager
from pikaraoke.lib.youtube_dl import upgrade_youtubedl
from pikaraoke.routes_fastapi.socket_events import setup_socket_events

# ---------------------------------------------------------------------------
# Socket.IO (ASGI mode — same python-socketio library, no Flask-SocketIO)
# ---------------------------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    engineio_logger=False,
)

# Suppress noisy engineio protocol-mismatch messages
_engineio_logger = logging.getLogger("engineio.server")
if _engineio_logger.level == logging.NOTSET:
    _engineio_logger.setLevel(logging.WARNING)

# Thread pool for CPU-bound work (PyTorch stem splitting, CREPE pitch extraction)
thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="karaoke-worker")


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize Karaoke engine on startup, clean up on shutdown."""
    import sys as _sys
    from pikaraoke.karaoke import Karaoke

    # When launched via `uvicorn pikaraoke.app_fastapi:combined`, sys.argv contains
    # uvicorn's args (e.g. "--host", "0.0.0.0") which confuse pikaraoke's argparse.
    # Keep only recognized pikaraoke flags AND their following value tokens.
    _RECOGNIZED = (
        "--hide", "--show", "--high", "--normalize", "--splash",
        "--download", "--vocal", "--disable", "--enable", "--logo",
        "--prefer", "--url", "--admin", "--bg-", "--config",
        "--preferred", "--streaming", "--ytdl", "--limit",
        "--avsync", "--cdg", "--buffer", "--dolphly",
        "--youtubedl", "--window", "--external", "--log",
        "-p", "-d", "-v", "-n", "-s", "-t", "-c", "-b", "-l", "-u",
    )
    original_argv = _sys.argv[:]
    raw = _sys.argv[1:]
    filtered: list[str] = []
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg.startswith(_RECOGNIZED):
            filtered.append(arg)
            # Consume all following non-flag tokens as values for this arg
            while i + 1 < len(raw) and not raw[i + 1].startswith("-"):
                i += 1
                filtered.append(raw[i])
        i += 1
    _sys.argv = [_sys.argv[0]] + filtered

    args = parse_pikaraoke_args()

    # Restore original argv
    _sys.argv = original_argv

    # --- Logging ---
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=int(args.log_level),
    )

    if not is_ffmpeg_installed():
        logging.error("ffmpeg is not installed. See: https://www.ffmpeg.org/")
        sys.exit(1)

    if not has_js_runtime():
        logging.warning("No JS runtime installed. Some yt-dlp downloads may fail.")

    # Create download directory
    if not os.path.exists(args.download_path):
        os.makedirs(args.download_path)

    # --- Initialize Karaoke engine ---
    k = Karaoke(
        port=args.port,
        download_path=args.download_path,
        youtubedl_proxy=args.youtubedl_proxy,
        splash_delay=args.splash_delay,
        log_level=args.log_level,
        volume=args.volume,
        normalize_audio=args.normalize_audio,
        complete_transcode_before_play=args.complete_transcode_before_play,
        buffer_size=args.buffer_size,
        hide_url=args.hide_url,
        hide_notifications=args.hide_notifications,
        hide_splash_screen=args.hide_splash_screen,
        high_quality=args.high_quality,
        logo_path=args.logo_path,
        hide_overlay=args.hide_overlay,
        show_splash_clock=args.show_splash_clock,
        url=args.url,
        prefer_hostname=args.prefer_hostname,
        disable_bg_music=args.disable_bg_music,
        bg_music_volume=args.bg_music_volume,
        bg_music_path=args.bg_music_path,
        disable_bg_video=args.disable_bg_video,
        bg_video_path=args.bg_video_path,
        disable_score=args.disable_score,
        limit_user_songs_by=args.limit_user_songs_by,
        avsync=float(args.avsync) if args.avsync is not None else None,
        config_file_path=args.config_file_path,
        cdg_pixel_scaling=args.cdg_pixel_scaling,
        streaming_format=args.streaming_format,
        additional_ytdl_args=getattr(args, "ytdl_args", None),
        socketio=sio,
        preferred_language=args.preferred_language,
        vocal_splitter=args.vocal_splitter,
    )

    # Wire dependencies for route injection
    configure_deps(
        karaoke=k,
        sio=sio,
        admin_password=args.admin_password,
        site_name="HomeKaraoke",
    )

    # Store on app state for access in routes
    app.state.karaoke = k
    app.state.boot_id = str(int(__import__("time").time()))
    app.state.thread_pool = thread_pool

    # Upgrade yt-dlp in background
    loop = asyncio.get_running_loop()

    # Store event loop reference for thread-safe SocketIO emits from run loop thread
    k._loop = loop

    # Thread-safe emit helper — events fire from both async routes and sync run loop
    def _safe_emit(event, data=None, **kwargs):
        coro = sio.emit(event, data, **kwargs)
        try:
            asyncio.get_running_loop()
            asyncio.ensure_future(coro)
        except RuntimeError:
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)

    # Wire events to SocketIO broadcasts (thread-safe)
    k.events.on("download_started", lambda: _safe_emit("download_started", namespace="/"))
    k.events.on("download_stopped", lambda: _safe_emit("download_stopped", namespace="/"))
    k.events.on("queue_update", lambda: _safe_emit("queue_update", namespace="/"))
    k.events.on("now_playing_update", lambda: _safe_emit("now_playing", k.get_now_playing(), namespace="/"))
    k.events.on("playback_started", lambda: _safe_emit("now_playing", k.get_now_playing(), namespace="/"))
    k.events.on("song_ended", lambda: _safe_emit("now_playing", k.get_now_playing(), namespace="/"))
    k.events.on("skip_requested", lambda: k.playback_controller.skip(False))
    k.events.on(
        "notification",
        lambda msg, cat="info": _safe_emit("notification", f"{msg}::is-{cat}", namespace="/"),
    )

    loop.run_in_executor(thread_pool, upgrade_youtubedl)

    # Start karaoke run loop in a background thread (it uses time.sleep internally)
    loop.run_in_executor(thread_pool, k.run)

    logging.info(f"HomeKaraoke v{VERSION} ready at http://0.0.0.0:{args.port}")
    logging.info(f"Connect player to: http://0.0.0.0:{args.port}/splash")

    yield  # App is running

    # --- Shutdown ---
    logging.info("Shutting down HomeKaraoke...")
    k.stop()
    delete_tmp_dir()
    thread_pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
fastapi_app = FastAPI(
    title="HomeKaraoke API",
    version=VERSION,
    lifespan=lifespan,
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Base path — read from env so API routes align with the Svelte build prefix.
# Set BASE_PATH=/karaoke when building the frontend and running the server.
# Leave empty to run at root (classic pikaraoke behaviour).
# ---------------------------------------------------------------------------
_BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")

# ---------------------------------------------------------------------------
# Register API routers
# ---------------------------------------------------------------------------
from pikaraoke.routes_fastapi.admin import router as admin_router
from pikaraoke.routes_fastapi.background_music import router as bg_music_router
from pikaraoke.routes_fastapi.controller import router as controller_router
from pikaraoke.routes_fastapi.files import router as files_router
from pikaraoke.routes_fastapi.images import router as images_router
from pikaraoke.routes_fastapi.info import router as info_router
from pikaraoke.routes_fastapi.metadata_api import router as metadata_router
from pikaraoke.routes_fastapi.now_playing import router as nowplaying_router
from pikaraoke.routes_fastapi.preferences import router as preferences_router
from pikaraoke.routes_fastapi.queue import router as queue_router
from pikaraoke.routes_fastapi.search import router as search_router
from pikaraoke.routes_fastapi.stream import router as stream_router
from pikaraoke.routes_fastapi.lyrics import router as lyrics_router
from pikaraoke.routes_fastapi.pitch import router as pitch_router
from pikaraoke.routes_fastapi.vocal import router as vocal_router

for r in [
    controller_router,
    queue_router,
    search_router,
    stream_router,
    nowplaying_router,
    vocal_router,
    lyrics_router,
    pitch_router,
    bg_music_router,
    images_router,
    info_router,
    preferences_router,
    admin_router,
    files_router,
    metadata_router,
]:
    fastapi_app.include_router(r, prefix=_BASE_PATH)

# Socket.IO events
setup_socket_events(sio)

# ---------------------------------------------------------------------------
# Static files / SPA catch-all
# ---------------------------------------------------------------------------

# Serve legacy static assets (fonts, images, sounds)
_legacy_static = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_legacy_static):
    fastapi_app.mount("/static", StaticFiles(directory=_legacy_static), name="legacy-static")

# Serve Svelte build output (production)
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    # Mount SPA assets at both prefixed and bare /_app paths
    _app_dir = os.path.join(_frontend_dist, "_app")
    if os.path.isdir(_app_dir):
        fastapi_app.mount("/_app", StaticFiles(directory=_app_dir), name="spa-app")
        if _BASE_PATH:
            fastapi_app.mount(f"{_BASE_PATH}/_app", StaticFiles(directory=_app_dir), name="spa-app-prefixed")

    # Catch-all — static file first, then index.html SPA fallback
    @fastapi_app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        clean_path = full_path.removeprefix(_BASE_PATH.lstrip("/")).lstrip("/") if _BASE_PATH else full_path
        file_path = os.path.join(_frontend_dist, clean_path) if clean_path else ""
        if clean_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))

# ---------------------------------------------------------------------------
# Combined ASGI app (Socket.IO wraps FastAPI)
# Socket.IO path must match the `path` option in the Svelte socket.io-client.
# ---------------------------------------------------------------------------
_sio_path = f"{_BASE_PATH}/socket.io" if _BASE_PATH else "/socket.io"
combined = socketio.ASGIApp(sio, fastapi_app, socketio_path=_sio_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_pikaraoke_args()
    uvicorn.run(
        "pikaraoke.app_fastapi:combined",
        host="0.0.0.0",
        port=int(args.port),
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
