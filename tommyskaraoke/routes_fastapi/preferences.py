"""User preferences management routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tommyskaraoke.lib.dependencies import broadcast_event, get_admin_password, get_karaoke
from tommyskaraoke.lib.preference_manager import PreferenceManager

router = APIRouter(tags=["preferences"])

_SCORE_PHRASE_KEYS = {"low_score_phrases", "mid_score_phrases", "high_score_phrases"}


def _is_admin(request: Request) -> bool:
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


def _get_active_score_phrases(k) -> dict:
    result = {}
    for tier in ("low", "mid", "high"):
        stored = getattr(k, f"{tier}_score_phrases")
        if stored:
            sep = "|" if "|" in stored else "\n"
            result[tier] = [p.strip() for p in stored.split(sep) if p.strip()]
        else:
            result[tier] = []
    return result


@router.get("/change_preferences")
async def change_preferences(request: Request, pref: str, val: str):
    """Change a user preference setting."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    success, message = k.preferences.set(pref, val)
    if success:
        await broadcast_event("preferences_update", {"key": pref, "value": val})
        if pref in _SCORE_PHRASE_KEYS:
            await broadcast_event("score_phrases_update", _get_active_score_phrases(k))
    return [success, message]


@router.get("/clear_preferences")
async def clear_preferences(request: Request):
    """Reset all preferences to defaults."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    success, message = k.preferences.reset_all()
    if success:
        k.update_now_playing_socket()
        await broadcast_event("preferences_reset", PreferenceManager.DEFAULTS)
        await broadcast_event("score_phrases_update", _get_active_score_phrases(k))
    return {"ok": success, "message": message}
