"""Home page route."""

import flask_babel
from flask import render_template, request, url_for
from flask_smorest import Blueprint

from tommyskaraoke.lib.current_app import get_karaoke_instance, get_site_name, is_admin

_ = flask_babel.gettext


home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def home():
    """Home page with now playing info and controls."""
    k = get_karaoke_instance()
    site_name = get_site_name()
    external_url = request.url_root.rstrip("/")
    return render_template(
        "home.html",
        site_title=site_name,
        title="Home",
        transpose_value=k.playback_controller.now_playing_transpose,
        admin=is_admin(),
        is_transpose_enabled=k.is_transpose_enabled,
        volume=k.volume,
        stem_separation_enabled=k.stem_separation_enabled,
        url=external_url,
        qr_code_url=url_for("images.qrcode"),
    )
