"""Per-song configuration — timing offsets and other user adjustments."""

import json
import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

from pikaraoke.lib.dependencies import get_karaoke

router = APIRouter(tags=["song_config"])

CONFIG_FILE = "song_config.json"


def _config_path() -> str:
    k = get_karaoke()
    return os.path.join(k.download_path, CONFIG_FILE)


def _load() -> dict:
    path = _config_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    path = _config_path()
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_song_config(song_basename: str) -> dict:
    """Get config for a song by basename. Returns empty dict if none."""
    name = os.path.splitext(song_basename)[0]
    return _load().get(name, {})


def get_all_configs() -> dict:
    """Get all song configs keyed by basename (no extension)."""
    return _load()


class SongConfigBody(BaseModel):
    lyrics_offset_ms: int | None = None
    pitch_offset_sec: float | None = None
    noise_gate: float | None = None
    backing_noise_gate: float | None = None
    merge_gap: float | None = None
    merge_semitones: int | None = None


# Fields and their "default" values — when set to default, they get removed from config
_CONFIG_DEFAULTS: dict[str, int | float] = {
    "lyrics_offset_ms": 0,
    "pitch_offset_sec": 0,
    "noise_gate": 0.05,
    "backing_noise_gate": 0.05,
    "merge_gap": 0.08,
    "merge_semitones": 0,
}


@router.post("/api/song_config/{song_basename}")
async def set_song_config(song_basename: str, body: SongConfigBody):
    """Save per-song configuration (offsets, noise gate, etc.)."""
    name = os.path.splitext(song_basename)[0]
    data = _load()
    cfg = data.get(name, {})

    for field, default in _CONFIG_DEFAULTS.items():
        val = getattr(body, field, None)
        if val is not None:
            if val == default:
                cfg.pop(field, None)
            else:
                cfg[field] = val

    if cfg:
        data[name] = cfg
    else:
        data.pop(name, None)

    _save(data)
    return {"ok": True, "config": cfg}


@router.get("/api/song_config/{song_basename}")
async def read_song_config(song_basename: str):
    """Get per-song configuration."""
    return get_song_config(song_basename)
