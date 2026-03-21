"""Stem mixer API routes."""

import os
from urllib.parse import unquote

from flask import jsonify, send_file
from flask_smorest import Blueprint

from pikaraoke.constants import STEMS_SUBDIR
from pikaraoke.lib.current_app import get_karaoke_instance

vocal_bp = Blueprint("vocal", __name__)


@vocal_bp.route("/stem_debug/<msg>")
def stem_debug(msg: str):
    """Debug endpoint for splash stem mixer logging."""
    import logging
    logging.info("[STEM-DEBUG] %s", msg)
    return jsonify({"ok": True})


@vocal_bp.route("/stem_toggle/<stem>")
def stem_toggle(stem: str):
    """Toggle a stem on/off in the mix."""
    k = get_karaoke_instance()
    if not k.vocal_splitter_enabled:
        return jsonify({"error": "Stem splitter not enabled"}), 400
    if not k.toggle_stem(stem):
        return jsonify({"error": f"Invalid stem: {stem}"}), 400
    return jsonify({"stem_mix": k.stem_mix})


@vocal_bp.route("/stem_mix")
def get_stem_mix():
    """Return current stem mix state."""
    k = get_karaoke_instance()
    return jsonify(
        {
            "vocal_splitter_enabled": k.vocal_splitter_enabled,
            "stem_mix": k.stem_mix,
        }
    )


@vocal_bp.route("/stems/<path:filepath>")
def serve_stem(filepath: str):
    """Serve a stem M4A file.

    URL pattern: /stems/{song_basename}/{stem}.m4a
    """
    k = get_karaoke_instance()
    stems_dir = os.path.join(k.download_path, STEMS_SUBDIR)
    safe_path = os.path.normpath(os.path.join(stems_dir, unquote(filepath)))

    # Prevent directory traversal
    if not safe_path.startswith(os.path.normpath(stems_dir) + os.sep):
        return jsonify({"error": "Invalid path"}), 403

    if not os.path.isfile(safe_path):
        return jsonify({"error": "Stem not found"}), 404

    return send_file(safe_path, mimetype="audio/mp4")
