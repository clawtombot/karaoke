"""Vocal splitter API routes."""

import os

from flask import jsonify, redirect, request, url_for
from flask_smorest import Blueprint

from pikaraoke.lib.current_app import get_karaoke_instance

vocal_bp = Blueprint("vocal", __name__)


@vocal_bp.route("/get_vocal_todo_list/<device_type>")
def get_vocal_todo_list(device_type: str):
    """Return the queue and vocal splitter config for the worker process.

    The worker polls this endpoint to find songs that need processing.
    """
    k = get_karaoke_instance()
    queue = k.queue_manager.queue
    songs = k.song_manager.songs

    # Build list of all known file basenames (queue + library)
    all_files = list({os.path.basename(s) for s in songs})
    for item in queue:
        bn = os.path.basename(item.get("file", ""))
        if bn and bn not in all_files:
            all_files.append(bn)

    return jsonify(
        {
            "download_path": k.download_path,
            "use_DNN": True,
            "queue": [os.path.join(k.download_path, f) for f in all_files],
        }
    )


@vocal_bp.route("/vocal_mode/<mode>")
def set_vocal_mode(mode: str):
    """Switch vocal playback mode.

    Args:
        mode: 'mixed' | 'vocal' | 'nonvocal'
    """
    k = get_karaoke_instance()
    if not k.vocal_splitter_enabled:
        return jsonify({"error": "Vocal splitter not enabled"}), 400
    if not k.set_vocal_mode(mode):
        return jsonify({"error": f"Invalid mode: {mode}"}), 400
    return jsonify({"vocal_mode": k.vocal_mode})


@vocal_bp.route("/vocal_mode")
def get_vocal_mode():
    """Return current vocal mode and splitter status."""
    k = get_karaoke_instance()
    return jsonify(
        {
            "vocal_splitter_enabled": k.vocal_splitter_enabled,
            "vocal_mode": k.vocal_mode,
        }
    )
