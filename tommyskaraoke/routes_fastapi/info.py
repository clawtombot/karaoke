"""System information and stats routes."""

from __future__ import annotations

import psutil
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tommyskaraoke import VERSION
from tommyskaraoke.constants import LANGUAGES, get_stem_separation_options
from tommyskaraoke.lib.dependencies import get_admin_password, get_karaoke, get_site_name
from tommyskaraoke.lib.get_platform import get_platform

router = APIRouter(tags=["info"])


def _is_admin(request: Request) -> bool:
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


@router.get("/info")
async def info(request: Request):
    """System information and settings."""
    k = get_karaoke()
    site_name = get_site_name()
    admin_password = get_admin_password()
    is_linux = get_platform() == "linux"
    preferred_language = k.preferences.get("preferred_language", "en")

    return {
        "site_title": site_name,
        "title": "Info",
        "url": k.url,
        "admin": _is_admin(request),
        "admin_password": admin_password,
        "platform": k.platform,
        "os_version": k.os_version,
        "ffmpeg_version": k.ffmpeg_version,
        "is_transpose_enabled": k.is_transpose_enabled,
        "youtubedl_version": k.youtubedl_version,
        "tommyskaraoke_version": VERSION,
        "cpu": None,
        "memory": None,
        "disk": None,
        "is_pi": k.is_raspberry_pi,
        "is_linux": is_linux,
        "volume": int(k.volume * 100),
        "bg_music_volume": int(k.bg_music_volume * 100),
        "disable_bg_music": k.disable_bg_music,
        "disable_bg_video": k.disable_bg_video,
        "disable_score": k.disable_score,
        "hide_notifications": k.hide_notifications,
        "show_splash_clock": k.show_splash_clock,
        "hide_url": k.hide_url,
        "hide_overlay": k.hide_overlay,
        "screensaver_timeout": k.screensaver_timeout,
        "splash_delay": k.splash_delay,
        "normalize_audio": k.normalize_audio,
        "cdg_pixel_scaling": k.cdg_pixel_scaling,
        "high_quality": k.high_quality,
        "complete_transcode_before_play": k.complete_transcode_before_play,
        "avsync": k.avsync,
        "limit_user_songs_by": k.limit_user_songs_by,
        "enable_fair_queue": k.enable_fair_queue,
        "buffer_size": k.buffer_size,
        "languages": LANGUAGES,
        "preferred_language": preferred_language,
        "browse_results_per_page": k.browse_results_per_page,
        "stem_separation": {
            "enabled": k.stem_separation_enabled,
            "backend": k.separation_backend,
            "device": k.separation_device,
            "model": k.separation_model,
            "vocal_model": k.vocal_split_model,
            "model_cache_dir": k.model_cache_dir,
            "options": get_stem_separation_options(),
        },
        "score_phrases": {
            "low": k.low_score_phrases,
            "mid": k.mid_score_phrases,
            "high": k.high_score_phrases,
        },
    }


@router.get("/info/stats")
async def get_system_stats(request: Request):
    """Get system statistics (CPU, Memory, Disk)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    try:
        cpu = str(psutil.cpu_percent(interval=1)) + "%"
    except Exception:
        cpu = "CPU usage query unsupported"

    memory = psutil.virtual_memory()
    available = round(memory.available / 1024.0 / 1024.0, 1)
    total_mem = round(memory.total / 1024.0 / 1024.0, 1)
    memory_str = f"{available}MB free / {total_mem}MB total ( {memory.percent}% )"

    disk = psutil.disk_usage("/")
    free = round(disk.free / 1024.0 / 1024.0 / 1024.0, 1)
    total_disk = round(disk.total / 1024.0 / 1024.0 / 1024.0, 1)
    disk_str = f"{free}GB free / {total_disk}GB total ( {disk.percent}% )"

    return {"cpu": cpu, "memory": memory_str, "disk": disk_str}
