"""User preferences management routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tommyskaraoke.lib.dependencies import broadcast_event, get_admin_password, get_karaoke
from tommyskaraoke.lib.preference_manager import PreferenceManager
from tommyskaraoke.lib.separation import resolve_separation_config

router = APIRouter(tags=["preferences"])

_SCORE_PHRASE_KEYS = {"low_score_phrases", "mid_score_phrases", "high_score_phrases"}
_STEM_SEPARATION_KEYS = {
    "stem_separation_enabled",
    "separation_backend",
    "separation_device",
    "separation_model",
    "vocal_split_model",
    "model_cache_dir",
}


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


def _coerce_pref_value(pref: str, val: str):
    default = PreferenceManager.DEFAULTS.get(pref)
    if isinstance(default, bool):
        return val.lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int) and val.lstrip("-").isdigit():
        return int(val)
    if isinstance(default, float):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _preview_stem_separation_change(k, pref: str, val: str) -> None:
    candidate = {
        "stem_separation_enabled": k.stem_separation_enabled,
        "separation_backend": k.separation_backend,
        "separation_device": k.separation_device,
        "separation_model": k.separation_model,
        "vocal_split_model": k.vocal_split_model,
        "model_cache_dir": k.model_cache_dir,
    }
    candidate[pref] = _coerce_pref_value(pref, val)
    resolve_separation_config(
        enabled=bool(candidate["stem_separation_enabled"]),
        backend=candidate["separation_backend"] or None,
        model=candidate["separation_model"] or None,
        vocal_split_model=candidate["vocal_split_model"] or None,
        device=candidate["separation_device"] or None,
        model_cache_dir=candidate["model_cache_dir"] or None,
    )


@router.get("/change_preferences")
async def change_preferences(request: Request, pref: str, val: str):
    """Change a user preference setting."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)
    k = get_karaoke()
    if pref in _STEM_SEPARATION_KEYS:
        try:
            _preview_stem_separation_change(k, pref, val)
        except ValueError as err:
            return JSONResponse({"ok": False, "error": str(err)}, status_code=400)

    success, message = k.preferences.set(pref, val)
    if success:
        if pref in _STEM_SEPARATION_KEYS:
            try:
                k.reload_stem_splitter()
            except ValueError as err:
                return JSONResponse({"ok": False, "error": str(err)}, status_code=400)
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
