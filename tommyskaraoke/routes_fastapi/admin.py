"""Admin routes for system control and authentication."""

from __future__ import annotations

import datetime
import subprocess
import sys
import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tommyskaraoke.karaoke import Karaoke
from tommyskaraoke.lib.dependencies import broadcast_event, get_admin_password, get_karaoke
from tommyskaraoke.lib.youtube_dl import upgrade_youtubedl

router = APIRouter(tags=["admin"])


def _is_admin(request: Request) -> bool:
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


def _delayed_halt(cmd: int, k: Karaoke) -> None:
    time.sleep(1.5)
    k.queue_manager.queue_clear()
    k.stop()
    if cmd == 0:
        sys.exit()
    elif cmd == 1:
        subprocess.run(["shutdown", "now"], check=False)
    elif cmd == 2:
        subprocess.run(["reboot"], check=False)
    elif cmd == 3:
        process = subprocess.Popen(["raspi-config", "--expand-rootfs"])
        process.wait()
        subprocess.run(["reboot"], check=False)


@router.get("/update_ytdl")
async def update_ytdl(request: Request):
    """Update yt-dlp to the latest version."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()

    def _do_update():
        time.sleep(3)
        k.youtubedl_version = upgrade_youtubedl()

    th = threading.Thread(target=_do_update)
    th.start()
    return {"ok": True, "message": "Updating youtube-dl! Should take a minute or two..."}


@router.get("/refresh")
async def refresh(request: Request):
    """Refresh the available songs list."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    k.song_manager.refresh_songs()
    return {"ok": True}


@router.get("/quit")
async def quit(request: Request):
    """Exit the TommysKaraoke application."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    msg = "Exiting tommyskaraoke now!"
    k.send_notification(msg, "danger")
    await broadcast_event("quit", msg)
    th = threading.Thread(target=_delayed_halt, args=[0, k])
    th.start()
    return {"ok": True, "message": msg}


@router.get("/shutdown")
async def shutdown(request: Request):
    """Shut down the host system."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    msg = "Shutting down system now!"
    k.send_notification(msg, "danger")
    await broadcast_event("shutdown", msg)
    th = threading.Thread(target=_delayed_halt, args=[1, k])
    th.start()
    return {"ok": True, "message": msg}


@router.get("/reboot")
async def reboot(request: Request):
    """Reboot the host system."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    msg = "Rebooting system now!"
    k.send_notification(msg, "danger")
    await broadcast_event("reboot", msg)
    th = threading.Thread(target=_delayed_halt, args=[2, k])
    th.start()
    return {"ok": True, "message": msg}


@router.get("/expand_fs")
async def expand_fs(request: Request):
    """Expand filesystem on Raspberry Pi."""
    k = get_karaoke()
    if not k.is_raspberry_pi:
        return JSONResponse(
            {"ok": False, "error": "Cannot expand fs on non-raspberry pi devices!"},
            status_code=400,
        )
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    th = threading.Thread(target=_delayed_halt, args=[3, k])
    th.start()
    return {"ok": True, "message": "Expanding filesystem and rebooting system now!"}


class AuthBody(BaseModel):
    admin_password: str = ""
    next: str = "/"


@router.post("/auth")
async def auth(body: AuthBody):
    """Authenticate as admin and set cookie."""
    admin_password = get_admin_password()

    next_url = body.next if body.next.startswith("/") else "/"

    if body.admin_password == admin_password:
        expire_date = datetime.datetime.now() + datetime.timedelta(days=90)
        response = JSONResponse({"ok": True, "message": "Admin mode granted!", "next": next_url})
        response.set_cookie("admin", admin_password, expires=expire_date)
        return response
    else:
        return JSONResponse(
            {"ok": False, "error": "Incorrect admin password!", "next": next_url},
            status_code=401,
        )


@router.get("/login")
async def login():
    """Admin login info endpoint."""
    return {"ok": True, "message": "Send POST /auth with admin_password to authenticate."}


@router.get("/logout")
async def logout():
    """Log out of admin mode."""
    response = JSONResponse({"ok": True, "message": "Logged out of admin mode!"})
    response.set_cookie("admin", "", max_age=0)
    return response
