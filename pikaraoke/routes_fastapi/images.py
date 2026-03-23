"""Image serving routes for QR code and logo."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from pikaraoke.lib.dependencies import get_karaoke

router = APIRouter(tags=["images"])


@router.get("/qrcode")
async def qrcode():
    """Get QR code image for the web interface URL."""
    k = get_karaoke()
    return FileResponse(k.qr_code_path, media_type="image/png")


@router.get("/logo")
async def logo():
    """Get the PiKaraoke logo image."""
    k = get_karaoke()
    return FileResponse(os.path.abspath(k.logo_path), media_type="image/png")
