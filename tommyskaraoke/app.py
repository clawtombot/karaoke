"""Flask application entry point and server initialization."""

from gevent import monkey, spawn

monkey.patch_all()

import logging
import os
import sys
from urllib.parse import quote

import flask_babel
from flask import Flask, request, session
from flask_babel import Babel
from flask_socketio import SocketIO

from tommyskaraoke import VERSION, karaoke
from tommyskaraoke.constants import LANGUAGES
from tommyskaraoke.lib.args import parse_tommyskaraoke_args
from tommyskaraoke.lib.browser import Browser
from tommyskaraoke.lib.current_app import get_karaoke_instance
from tommyskaraoke.lib.ffmpeg import is_ffmpeg_installed
from tommyskaraoke.lib.file_resolver import delete_tmp_dir
from tommyskaraoke.lib.get_platform import (
    get_data_directory,
    get_platform,
    has_js_runtime,
    is_windows,
)
from tommyskaraoke.lib.song_manager import SongManager
from tommyskaraoke.lib.youtube_dl import upgrade_youtubedl
from tommyskaraoke.routes.admin import admin_bp
from tommyskaraoke.routes.background_music import background_music_bp
from tommyskaraoke.routes.batch_song_renamer import batch_song_renamer_bp
from tommyskaraoke.routes.controller import controller_bp
from tommyskaraoke.routes.files import files_bp
from tommyskaraoke.routes.home import home_bp
from tommyskaraoke.routes.images import images_bp
from tommyskaraoke.routes.info import info_bp
from tommyskaraoke.routes.metadata_api import metadata_bp
from tommyskaraoke.routes.now_playing import nowplaying_bp
from tommyskaraoke.routes.preferences import preferences_bp
from tommyskaraoke.routes.queue import queue_bp
from tommyskaraoke.routes.search import search_bp
from tommyskaraoke.routes.socket_events import setup_socket_events
from tommyskaraoke.routes.splash import splash_bp
from tommyskaraoke.routes.stream import stream_bp
from tommyskaraoke.routes.vocal import vocal_bp

_ = flask_babel.gettext

from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

args = parse_tommyskaraoke_args()

# Suppress noisy protocol-mismatch messages from health-check clients (e.g. NanoClaw
# proxy) that connect with a different Engine.IO version. These are harmless but
# appear as ERROR in the default engineio logger, so we cap them at WARNING.
_engineio_logger = logging.getLogger("engineio.server")
if _engineio_logger.level == logging.NOTSET:
    _engineio_logger.setLevel(logging.WARNING)

# Allow all origins for Socket.IO since the app may be accessed via reverse proxy
# (e.g., Tailscale) where the origin differs from the local server URL
socketio = SocketIO(async_mode="gevent", cors_allowed_origins="*", engineio_logger=False)
babel = Babel()


class ReverseProxyMiddleware:
    """Set SCRIPT_NAME from X-Forwarded-Prefix so url_for() includes the proxy prefix."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_FORWARDED_PREFIX", "")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(prefix):
                environ["PATH_INFO"] = path_info[len(prefix) :]
        return self.wsgi_app(environ, start_response)


app = Flask(__name__)
app.wsgi_app = ReverseProxyMiddleware(app.wsgi_app)
app.secret_key = os.urandom(24)
app.jinja_env.add_extension("jinja2.ext.i18n")
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"
app.config["JSON_SORT_KEYS"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # No cache during development


@app.after_request
def add_no_cache_for_js(response):
    """Prevent browser from caching JS files so code changes take effect immediately."""
    if request.path.endswith(".js"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Always initialize flask-smorest Api for error handling (@bp.arguments validation).
# Only expose the Swagger UI when --enable-swagger is passed.
from flask_smorest import Api

app.config["API_TITLE"] = "TommysKaraoke API"
app.config["API_VERSION"] = VERSION
app.config["VERSION"] = VERSION
app.config["BOOT_ID"] = str(int(__import__("time").time()))
app.config["OPENAPI_VERSION"] = "3.0.2"
app.config["OPENAPI_URL_PREFIX"] = "/"

if args.enable_swagger:
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/apidocs"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

api = Api(app)

# Blueprints shown in /apidocs when swagger is enabled
_api_blueprints = [
    queue_bp,
    search_bp,
    files_bp,
    preferences_bp,
    admin_bp,
    controller_bp,
    background_music_bp,
    images_bp,
    nowplaying_bp,
    stream_bp,
    metadata_bp,
    vocal_bp,
]

# Blueprints hidden from /apidocs (internal UI routes)
_internal_blueprints = [
    home_bp,
    info_bp,
    splash_bp,
    batch_song_renamer_bp,
]

for bp in _api_blueprints:
    api.register_blueprint(bp)

for bp in _internal_blueprints:
    app.register_blueprint(bp)


def get_locale() -> str | None:
    """Select the language to display based on user preference or Accept-Language header.

    Returns:
        Language code string (e.g., 'en', 'fr') or None.
    """
    # Check config.ini lang settings (if karaoke instance is initialized)
    try:
        k = get_karaoke_instance()
        preferred_lang = k.preferences.get("preferred_language")
        if preferred_lang and preferred_lang in LANGUAGES.keys():
            return preferred_lang
    except (RuntimeError, AttributeError):
        # App context not available or karaoke instance not initialized yet
        pass

    # Check URL arguments
    if request.args.get("lang"):
        session["lang"] = request.args.get("lang")
        locale = session.get("lang", "en")
    # Use browser header
    else:
        locale = request.accept_languages.best_match(LANGUAGES.keys())
    return locale


babel.init_app(app, locale_selector=get_locale)
socketio.init_app(app)
setup_socket_events(socketio)


def main() -> None:
    """Main entry point for the TommysKaraoke application.

    Initializes the Flask server, Karaoke engine, and splash screen.
    Blocks until the application is terminated.
    """
    platform = get_platform()

    args = parse_tommyskaraoke_args()

    # --- LOGGING SETUP ---
    # Optional: Force the log file to go to AppData too, so you can debug installation issues
    # log_path = os.path.join(get_data_directory(), 'tommyskaraoke.log')
    # logging.basicConfig(filename=log_path, level=logging.INFO)

    if not is_ffmpeg_installed():
        logging.error(
            "ffmpeg is not installed, which is required to run TommysKaraoke. See: https://www.ffmpeg.org/"
        )
        sys.exit(1)

    if not has_js_runtime():
        logging.warning(
            "No js runtime is installed (such as Deno, Bun, Node.js, or QuickJS). This is required to run yt-dlp. Some downloads may not work. See: https://github.com/yt-dlp/yt-dlp/wiki/EJS"
        )

    # setup/create download directory if necessary
    if not os.path.exists(args.download_path):
        print("Creating download path: " + args.download_path)
        os.makedirs(args.download_path)

    # Configure karaoke process
    k = karaoke.Karaoke(
        port=args.port,
        download_path=args.download_path,
        youtubedl_proxy=args.youtubedl_proxy,
        splash_delay=args.splash_delay,
        log_level=args.log_level,
        volume=args.volume,
        normalize_audio=args.normalize_audio,
        complete_transcode_before_play=args.complete_transcode_before_play,
        buffer_size=args.buffer_size,
        hide_url=args.hide_url,
        hide_notifications=args.hide_notifications,
        hide_splash_screen=args.hide_splash_screen,
        high_quality=args.high_quality,
        logo_path=args.logo_path,
        hide_overlay=args.hide_overlay,
        show_splash_clock=args.show_splash_clock,
        url=args.url,
        prefer_hostname=args.prefer_hostname,
        disable_bg_music=args.disable_bg_music,
        bg_music_volume=args.bg_music_volume,
        bg_music_path=args.bg_music_path,
        disable_bg_video=args.disable_bg_video,
        bg_video_path=args.bg_video_path,
        disable_score=args.disable_score,
        limit_user_songs_by=args.limit_user_songs_by,
        avsync=float(args.avsync) if args.avsync is not None else None,
        config_file_path=args.config_file_path,
        cdg_pixel_scaling=args.cdg_pixel_scaling,
        streaming_format=args.streaming_format,
        additional_ytdl_args=getattr(args, "ytdl_args", None),
        socketio=socketio,
        preferred_language=args.preferred_language,
        vocal_splitter=args.vocal_splitter,
        separation_backend=args.separation_backend,
        separation_device=args.separation_device,
        separation_model=args.separation_model,
        vocal_split_model=args.vocal_split_model,
        model_cache_dir=args.model_cache_dir,
    )

    # expose karaoke object to the flask app
    with app.app_context():
        app.config["KARAOKE_INSTANCE"] = k

    # Wire download events to SocketIO broadcasts with app context
    from tommyskaraoke.lib.current_app import broadcast_event

    def _broadcast_in_context(event_name):
        def handler():
            with app.app_context():
                broadcast_event(event_name)

        return handler

    k.events.on("download_started", _broadcast_in_context("download_started"))
    k.events.on("download_stopped", _broadcast_in_context("download_stopped"))

    # expose shared configuration variables to the flask app
    app.config["ADMIN_PASSWORD"] = args.admin_password
    app.config["SITE_NAME"] = "TommysKaraoke"

    # Expose some functions to jinja templates
    app.jinja_env.globals.update(filename_from_path=SongManager.filename_from_path)
    app.jinja_env.globals.update(url_escape=quote)

    spawn(upgrade_youtubedl)

    server = WSGIServer(
        ("0.0.0.0", int(args.port)),
        app,
        handler_class=WebSocketHandler,
        log=None,
        error_log=logging.getLogger(),
    )
    server.start()

    # Handle sigterm, apparently cherrypy won't shut down without explicit handling
    # signal.signal(signal.SIGTERM, lambda signum, stack_frame: k.stop())

    # force headless mode when on Android
    if (platform == "android") and not args.hide_splash_screen:
        args.hide_splash_screen = True
        logging.info("Forced to run headless mode in Android")

    # Start the splash screen browser
    if not args.hide_splash_screen:
        browser = Browser(k, args.window_size, args.external_monitor)
        browser.launch_splash_screen()
        if not browser:
            logging.error("Failed to launch splash screen browser")
            sys.exit()
    else:
        browser = None

    if args.enable_swagger:
        logging.info(f"Swagger API docs enabled at {k.url}/apidocs")

    # Start the karaoke process
    k.run()

    # Close running browser when done
    if browser is not None:
        browser.close()

    delete_tmp_dir()
    sys.exit()


if __name__ == "__main__":
    main()
