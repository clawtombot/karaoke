"""Helpers for presenting queue items alongside in-flight downloads."""

from __future__ import annotations

import os
from typing import Callable

from tommyskaraoke.constants import STEM_NAMES, STEMS_SUBDIR, VOCAL_SPLIT_STEMS, demucs_complete, stems_complete


def _artifact_exists(stem_dir: str, stem_name: str) -> bool:
    """Return whether a stem exists as either WAV-in-progress or final M4A."""
    return os.path.isfile(os.path.join(stem_dir, f'{stem_name}.wav')) or os.path.isfile(
        os.path.join(stem_dir, f'{stem_name}.m4a')
    )


def build_song_readiness(song_path: str, stem_separation_enabled: bool) -> dict:
    """Build end-to-end readiness for a downloaded song."""
    if not stem_separation_enabled:
        return {'step': 'Ready', 'detail': None, 'pending': False}

    basename = os.path.basename(song_path)
    stem_dir = os.path.join(os.path.dirname(song_path), STEMS_SUBDIR, basename)

    if not os.path.isdir(stem_dir):
        return {'step': 'Queued', 'detail': None, 'pending': True}

    if stems_complete(stem_dir):
        return {'step': 'Ready', 'detail': None, 'pending': False}

    if os.path.isfile(os.path.join(stem_dir, '.error')):
        return {'step': 'Failed', 'detail': 'Stem separation failed', 'pending': False}

    demucs_artifacts = sum(1 for name in STEM_NAMES if _artifact_exists(stem_dir, name))
    if not demucs_complete(stem_dir):
        detail = None
        if demucs_artifacts:
            detail = f'{demucs_artifacts}/{len(STEM_NAMES)}'
        return {'step': 'Separating stems', 'detail': detail, 'pending': True}

    vocal_artifacts = sum(1 for name in VOCAL_SPLIT_STEMS if _artifact_exists(stem_dir, name))
    vocal_final = sum(1 for name in VOCAL_SPLIT_STEMS if os.path.isfile(os.path.join(stem_dir, f'{name}.m4a')))
    if vocal_final == len(VOCAL_SPLIT_STEMS):
        return {'step': 'Ready', 'detail': None, 'pending': False}
    if vocal_artifacts == len(VOCAL_SPLIT_STEMS):
        return {'step': 'Finalizing', 'detail': None, 'pending': True}

    detail = None
    if vocal_artifacts:
        detail = f'{vocal_artifacts}/{len(VOCAL_SPLIT_STEMS)}'
    return {'step': 'Splitting vocals', 'detail': detail, 'pending': True}


def build_download_snapshot(download: dict | None) -> dict | None:
    """Normalize download state for UI consumption."""
    if not download:
        return None

    raw_status = download.get("status", "queued")
    step = {
        'queued': 'Queued',
        'starting': 'Downloading',
        'downloading': 'Downloading',
        'complete': 'Ready',
        'ready': 'Ready',
        'error': 'Failed',
    }.get(raw_status, str(raw_status).replace('_', ' ').title())
    detail = None
    if raw_status in {'starting', 'downloading'}:
        progress = max(0, min(100, round(float(download.get('progress', 0.0) or 0.0))))
        detail = f'{progress}%'
    elif raw_status == 'error':
        detail = 'Download failed'
    return {
        "step": step,
        "detail": detail,
        "pending": bool(download.get("pending", raw_status not in {"ready", "complete", "error"})),
    }


def build_visible_queue(
    queue: list[dict],
    downloads_status: dict | None,
    song_metadata: Callable[[str], dict],
    song_readiness: Callable[[str], dict],
) -> list[dict]:
    """Combine the real queue with auto-queued downloads still in progress."""
    items: list[dict] = []

    for item in queue:
        items.append(
            {
                **item,
                "meta": song_metadata(item["file"]),
                "download": song_readiness(item["file"]),
            }
        )

    if not isinstance(downloads_status, dict):
        return items

    pending_downloads: list[dict] = []
    active = downloads_status.get("active")
    if active and active.get("enqueue"):
        pending_downloads.append(active)
    pending_downloads.extend(d for d in downloads_status.get("pending", []) if d.get("enqueue"))

    for download in pending_downloads:
        display_title = download.get("display_title") or download.get("title") or download.get("url")
        items.append(
            {
                "file": f"__download__:{download['id']}",
                "title": display_title,
                "user": download.get("user", ""),
                "semitones": 0,
                "meta": None,
                "download": build_download_snapshot(download),
            }
        )

    return items


def get_up_next_item(
    queue: list[dict], downloads_status: dict | None, song_readiness: Callable[[str], dict]
) -> dict | None:
    """Return the next visible item, preferring the real queue over pending downloads."""
    if queue:
        return {
            "title": queue[0]["title"],
            "user": queue[0]["user"],
            "download": song_readiness(queue[0]["file"]),
        }

    if not isinstance(downloads_status, dict):
        return None

    active = downloads_status.get("active")
    if active and active.get("enqueue"):
        return {
            "title": active.get("display_title") or active.get("title") or active.get("url"),
            "user": active.get("user", ""),
            "download": build_download_snapshot(active),
        }

    for pending in downloads_status.get("pending", []):
        if pending.get("enqueue"):
            return {
                "title": pending.get("display_title") or pending.get("title") or pending.get("url"),
                "user": pending.get("user", ""),
                "download": build_download_snapshot(pending),
            }

    return None
