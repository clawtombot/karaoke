"""FastAPI dependency injection — replaces Flask current_app.py."""

from __future__ import annotations

import logging
from typing import Any

from tommyskaraoke.karaoke import Karaoke

# Module-level singleton — set once during startup, used by all routes via Depends()
_karaoke: Karaoke | None = None
_admin_password: str | None = None
_site_name: str = "TommysKaraoke"

# python-socketio AsyncServer — set during startup
_sio: Any = None


def configure(
    karaoke: Karaoke,
    sio: Any,
    admin_password: str | None = None,
    site_name: str = "TommysKaraoke",
) -> None:
    """Called once at startup to wire the singleton."""
    global _karaoke, _sio, _admin_password, _site_name
    _karaoke = karaoke
    _sio = sio
    _admin_password = admin_password
    _site_name = site_name


def get_karaoke() -> Karaoke:
    """FastAPI dependency: returns the Karaoke singleton."""
    if _karaoke is None:
        raise RuntimeError("Karaoke instance not initialized")
    return _karaoke


def get_sio():
    """FastAPI dependency: returns the python-socketio AsyncServer."""
    if _sio is None:
        raise RuntimeError("SocketIO not initialized")
    return _sio


def get_admin_password() -> str | None:
    return _admin_password


def get_site_name() -> str:
    return _site_name


async def broadcast_event(event: str, data: Any = None) -> None:
    """Broadcast a SocketIO event to all connected clients."""
    sio = get_sio()
    logging.debug("Broadcasting event: %s", event)
    await sio.emit(event, data, namespace="/")
