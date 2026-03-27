"""Core karaoke engine for managing songs, queue, and playback."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import time
from typing import Any

import qrcode
from flask_babel import _
from qrcode.image.pure import PyPNGImage

from tommyskaraoke.constants import ALL_STEM_NAMES, STEM_NAMES, VOCAL_SPLIT_STEMS, STEMS_SUBDIR, stems_complete
from tommyskaraoke.lib.download_manager import DownloadManager
from tommyskaraoke.lib.events import EventSystem
from tommyskaraoke.lib.ffmpeg import (
    get_ffmpeg_version,
    is_transpose_enabled,
    supports_hardware_h264_encoding,
)
from tommyskaraoke.lib.get_platform import (
    get_data_directory,
    get_os_version,
    get_platform,
    is_raspberry_pi,
)
from tommyskaraoke.lib.network import get_ip
from tommyskaraoke.lib.playback_controller import PlaybackController
from tommyskaraoke.lib.preference_manager import PreferenceManager
from tommyskaraoke.lib.queue_view import build_song_readiness, get_up_next_item
from tommyskaraoke.lib.queue_manager import QueueManager
from tommyskaraoke.lib.separation import SeparationConfig, apply_model_cache_env, resolve_separation_config
from tommyskaraoke.lib.song_manager import SongManager
from tommyskaraoke.lib.youtube_dl import (
    get_search_results,
    get_youtubedl_version,
    upgrade_youtubedl,
)
from tommyskaraoke.version import __version__ as VERSION


class Karaoke:
    """Main karaoke engine managing songs, queue, and playback.

    This class handles all core karaoke functionality including:
    - Song queue management
    - YouTube video downloading
    - Playback coordination via PlaybackController
    - User preferences
    - QR code generation

    Attributes:
        available_songs: List of available song file paths.
        queue_manager: Queue management for songs.
        playback_controller: Playback state and stream coordination.
        volume: Current volume level (0.0 to 1.0).
    """

    song_manager: SongManager
    queue_manager: QueueManager
    playback_controller: PlaybackController

    now_playing_notification: str | None = None
    volume: float

    # Stem splitter state
    stem_separation_enabled: bool = False
    _vocal_worker: subprocess.Popen | None = None
    separation_config: SeparationConfig | None = None
    separation_backend: str = ""
    separation_device: str = ""
    separation_model: str = ""
    vocal_split_model: str = ""
    model_cache_dir: str = ""

    qr_code_path: str | None = None
    base_path: str = os.path.dirname(__file__)
    loop_interval: int = 500  # in milliseconds
    default_logo_path: str = os.path.join(base_path, "static", "images", "logo.png")
    default_bg_music_path: str = os.path.join(base_path, "static", "music")
    default_bg_video_path: str = os.path.join(base_path, "static", "video", "night_sea.mp4")
    screensaver_timeout: int

    normalize_audio: bool
    show_splash_clock: bool

    # Download manager for serialized downloads
    download_manager: DownloadManager

    # Event system and preferences
    events: EventSystem
    preferences: PreferenceManager

    def __init__(
        self,
        # Non-preference parameters (keep their own defaults)
        additional_ytdl_args: str | None = None,
        bg_music_path: str | None = None,
        bg_video_path: str | None = None,
        config_file_path: str = "config.ini",
        download_path: str = "/usr/lib/tommyskaraoke/songs",
        hide_splash_screen: bool | None = None,
        log_level: int = logging.DEBUG,
        logo_path: str | None = None,
        port: int = 5555,
        prefer_hostname: bool | None = None,
        preferred_language: str | None = None,
        socketio=None,
        streaming_format: str = "hls",
        url: str | None = None,
        vocal_splitter: bool = False,
        separation_backend: str | None = None,
        separation_device: str | None = None,
        separation_model: str | None = None,
        vocal_split_model: str | None = None,
        model_cache_dir: str | None = None,
        youtubedl_proxy: str | None = None,
        # Preference parameters (defaults from PreferenceManager.DEFAULTS)
        avsync: float | None = None,
        bg_music_volume: float | None = None,
        browse_results_per_page: int | None = None,
        buffer_size: int | None = None,
        cdg_pixel_scaling: bool | None = None,
        complete_transcode_before_play: bool | None = None,
        disable_bg_music: bool | None = None,
        disable_bg_video: bool | None = None,
        disable_score: bool | None = None,
        hide_notifications: bool | None = None,
        hide_overlay: bool | None = None,
        hide_url: bool | None = None,
        high_quality: bool | None = None,
        limit_user_songs_by: int | None = None,
        normalize_audio: bool | None = None,
        screensaver_timeout: int | None = None,
        show_splash_clock: bool | None = None,
        splash_delay: int | None = None,
        volume: float | None = None,
    ) -> None:
        """Initialize the Karaoke instance.

        Args:
            port: HTTP server port number.
            download_path: Directory path for downloaded songs.
            hide_url: Hide URL and QR code on splash screen.
            hide_notifications: Disable notification popups.
            hide_splash_screen: Run in headless mode.
            high_quality: Download higher quality videos (up to 1080p).
            volume: Default volume level (0.0 to 1.0).
            normalize_audio: Apply loudness normalization.
            complete_transcode_before_play: Buffer entire file before playback.
            buffer_size: Transcode buffer size in KB.
            log_level: Logging level (e.g., logging.DEBUG).
            splash_delay: Seconds to wait between songs.
            youtubedl_proxy: Proxy URL for yt-dlp.
            logo_path: Custom logo image path.
            hide_overlay: Hide video overlay.
            screensaver_timeout: Screensaver activation delay in seconds.
            url: Override auto-detected URL.
            prefer_hostname: Use hostname instead of IP in URL.
            disable_bg_music: Disable background music.
            bg_music_volume: Background music volume (0.0 to 1.0).
            bg_music_path: Directory for background music files.
            bg_video_path: Path to background video file.
            disable_bg_video: Disable background video.
            disable_score: Disable score screen.
            limit_user_songs_by: Max songs per user in queue (0 = unlimited).
            avsync: Audio/video sync adjustment in seconds.
            config_file_path: Path to config.ini file.
            cdg_pixel_scaling: Enable CDG pixel scaling.
            streaming_format: Video streaming format ('hls' or 'mp4').
            browse_results_per_page: Number of search results per page.
            additional_ytdl_args: Additional yt-dlp command arguments.
            socketio: SocketIO instance for real-time event emission.
            preferred_language: Language code for UI (e.g., 'en', 'de_DE').
        """
        logging.basicConfig(
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=int(log_level),
        )

        # Initialize event system and preferences (foundation for all components)
        self.events = EventSystem()
        self.preferences = PreferenceManager(config_file_path, target=self)

        # Platform-specific initializations
        self.platform = get_platform()
        self.os_version = get_os_version()
        self.ffmpeg_version = get_ffmpeg_version()
        self.is_transpose_enabled = is_transpose_enabled()
        self.supports_hardware_h264_encoding = supports_hardware_h264_encoding()
        self.youtubedl_version = get_youtubedl_version()
        self.is_raspberry_pi = is_raspberry_pi()

        logging.info("TommysKaraoke version: " + VERSION)

        # Set non-preference attributes (not stored in config)
        self.port = port
        self.hide_splash_screen = hide_splash_screen
        self.download_path = download_path
        self.log_level = log_level
        self.youtubedl_proxy = youtubedl_proxy
        self.additional_ytdl_args = additional_ytdl_args
        self.logo_path = self.default_logo_path if logo_path is None else logo_path
        self.prefer_hostname = prefer_hostname
        self.bg_music_path = self.default_bg_music_path if bg_music_path is None else bg_music_path
        self.bg_video_path = self.default_bg_video_path if bg_video_path is None else bg_video_path
        self.streaming_format = streaming_format
        self.socketio = socketio
        self._loop: asyncio.AbstractEventLoop | None = None  # set by lifespan
        self.url_override = url
        self.url = self.get_url()

        # Load all preference-driven attributes from config (with CLI overrides as fallback)
        cli_args = {k: v for k, v in locals().items() if k != "self"}
        cli_args["stem_separation_enabled"] = vocal_splitter
        self._load_preferences(**cli_args)

        # Log the settings to debug level
        self.log_settings_to_debug()

        # Initialize song manager and load songs from download_path
        self.song_manager = SongManager(self.download_path)
        self.song_manager.refresh_songs()

        self.generate_qr_code()

        # Set preferred language from command line if provided (persists to config)
        if preferred_language:
            self.preferences.set("preferred_language", preferred_language)
            logging.info(f"Setting preferred language to: {preferred_language}")

        # Initialize playback controller for video playback and FFmpeg coordination
        self.playback_controller = PlaybackController(
            preferences=self.preferences,
            events=self.events,
            filename_from_path=SongManager.filename_from_path,
            streaming_format=self.streaming_format,
        )

        # Event bridging: the coordinator wires manager events to the UI (SocketIO/notifications).
        self.events.on("notification", self.log_and_send)
        self.events.on(
            "queue_update",
            lambda: self._emit("queue_update", namespace="/"),
        )
        # now_playing_update, playback_started, song_ended → wired in app_fastapi lifespan
        # (via _safe_emit for thread-safety). Don't duplicate here.
        self.events.on("skip_requested", lambda: self.playback_controller.skip(False))

        # Initialize queue manager
        self.queue_manager = QueueManager(
            preferences=self.preferences,
            events=self.events,
            get_now_playing_user=lambda: self.playback_controller.now_playing_user,
            filename_from_path=SongManager.filename_from_path,
            get_available_songs=lambda: self.song_manager.songs,
        )

        # Initialize and start download manager
        self.download_manager = DownloadManager(
            events=self.events,
            preferences=self.preferences,
            song_manager=self.song_manager,
            queue_manager=self.queue_manager,
            download_path=self.download_path,
            youtubedl_proxy=self.youtubedl_proxy,
            additional_ytdl_args=self.additional_ytdl_args,
        )
        self.download_manager.start()

        # Stem splitter setup
        self.boot_id = str(int(time.time()))
        self.stem_mix: dict[str, float] = {s: 1.0 for s in ALL_STEM_NAMES}
        if self.stem_separation_enabled:
            self.reload_stem_splitter()

    def _init_stem_splitter(self, config: SeparationConfig) -> None:
        """Set up 6-stem splitting: create output dir and launch the worker process."""
        apply_model_cache_env(config.model_cache_dir)

        stems_dir = os.path.join(self.download_path, STEMS_SUBDIR)
        os.makedirs(stems_dir, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "tommyskaraoke.lib.vocal_splitter",
            "--download-path",
            self.download_path,
            "--separation-backend",
            config.backend,
            "--separation-model",
            config.model,
            "--vocal-split-model",
            config.vocal_split_model,
        ]
        if config.device:
            cmd.extend(["--separation-device", config.device])
        if config.model_cache_dir:
            cmd.extend(["--model-cache-dir", config.model_cache_dir])

        logging.info("Starting stem splitter worker: %s", " ".join(cmd))
        self._vocal_worker = subprocess.Popen(
            cmd,
            env={**os.environ, **apply_model_cache_env(config.model_cache_dir)},
        )
        self.stem_separation_enabled = True

    def _stop_stem_splitter(self) -> None:
        """Stop the background stem splitter worker if it is running."""
        if self._vocal_worker is None:
            return

        self._vocal_worker.terminate()
        try:
            self._vocal_worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._vocal_worker.kill()
        self._vocal_worker = None

    def reload_stem_splitter(self) -> None:
        """Apply the current persisted stem separation settings to the worker."""
        self._stop_stem_splitter()
        self.separation_config = resolve_separation_config(
            enabled=self.stem_separation_enabled,
            backend=self.separation_backend or None,
            model=self.separation_model or None,
            vocal_split_model=self.vocal_split_model or None,
            device=self.separation_device or None,
            model_cache_dir=self.model_cache_dir or None,
        )
        if self.separation_config is None:
            self.stem_separation_enabled = False
            self.update_now_playing_socket()
            return

        self._init_stem_splitter(self.separation_config)
        self.update_now_playing_socket()

    def get_stem_paths(self, file_path: str) -> dict[str, str] | None:
        """Return dict of stem_name -> M4A path if all stems are ready, else None."""
        if not self.stem_separation_enabled:
            return None

        basename = os.path.basename(file_path)
        stem_dir = os.path.join(self.download_path, STEMS_SUBDIR, basename)
        if not os.path.isdir(stem_dir) or not stems_complete(stem_dir):
            return None

        # Use lead/backing vocals if available, otherwise fall back to combined vocals
        names = list(ALL_STEM_NAMES) if all(
            os.path.isfile(os.path.join(stem_dir, f"{s}.m4a")) for s in VOCAL_SPLIT_STEMS
        ) else list(STEM_NAMES)
        return {name: os.path.join(stem_dir, f"{name}.m4a") for name in names}

    def toggle_stem(self, stem: str) -> bool:
        """Toggle a stem on/off in the mix (0.0 <-> 1.0).

        Returns True if toggled, False if invalid stem name.
        """
        if stem not in ALL_STEM_NAMES and stem not in STEM_NAMES:
            return False
        self.stem_mix[stem] = 0.0 if self.stem_mix.get(stem, 1.0) > 0 else 1.0
        logging.info("Stem %s toggled to %s", stem, self.stem_mix[stem])
        self.update_now_playing_socket()
        return True

    def set_stem_volume(self, stem: str, volume: float) -> bool:
        """Set a stem's volume (0.0–1.0).

        Returns True if set, False if invalid stem name.
        """
        if stem not in ALL_STEM_NAMES and stem not in STEM_NAMES:
            return False
        self.stem_mix[stem] = max(0.0, min(1.0, volume))
        self.update_now_playing_socket()
        return True

    def _load_preferences(self, **cli_overrides: Any) -> None:
        """Load preference-driven attributes from config file.

        Priority: CLI argument (if provided) > config file > PreferenceManager.DEFAULTS
        """
        self.preferences.apply_all(**cli_overrides)

    def get_url(self):
        """Get the URL for accessing the TommysKaraoke web interface.

        On Raspberry Pi, retries getting the IP address for up to 30 seconds
        in case the network is still initializing at startup.

        Returns:
            URL string in format http://ip:port
        """
        if self.is_raspberry_pi:
            # retry in case pi is still starting up
            # and doesn't have an IP yet (occurs when launched from /etc/rc.local)
            end_time = int(time.time()) + 30
            while int(time.time()) < end_time:
                addresses_str = (
                    subprocess.check_output(["hostname", "-I"]).strip().decode("utf-8", "ignore")
                )
                addresses = addresses_str.split(" ")
                self.ip = addresses[0]
                if len(self.ip) < 7:
                    logging.debug("Couldn't get IP, retrying....")
                else:
                    break
        else:
            self.ip = get_ip(self.platform)

        logging.debug("IP address (for QR code and splash screen): " + self.ip)

        if self.url_override != None:
            logging.debug("Overriding URL with " + self.url_override)
            url = self.url_override
        else:
            if self.prefer_hostname:
                url = f"http://{socket.getfqdn().lower()}:{self.port}"
            else:
                url = f"http://{self.ip}:{self.port}"
        return url

    def log_settings_to_debug(self) -> None:
        """Log all current settings at debug level."""
        output = ""
        for key, value in sorted(vars(self).items()):
            output += f"  {key}: {value}\n"
        logging.debug("\n\n" + output)

    def generate_qr_code(self, url: str | None = None) -> None:
        """Generate a QR code image for the web interface URL.

        Args:
            url: Override URL to encode. If None, uses self.url.
                 Skips regeneration if the URL hasn't changed.
        """
        target_url = url or self.url
        if hasattr(self, "_qr_url") and self._qr_url == target_url:
            return
        logging.debug("Generating URL QR code for: %s", target_url)
        qr = qrcode.QRCode(
            version=1,
            box_size=1,
            border=4,
        )
        qr.add_data(target_url)
        qr.make()
        img = qr.make_image(image_factory=PyPNGImage)
        data_dir = get_data_directory()
        self.qr_code_path = os.path.join(data_dir, "qrcode.png")
        img.save(self.qr_code_path)  # type: ignore[arg-type]
        self._qr_url = target_url

    def send_notification(self, message: str, color: str = "primary") -> None:
        """Send a notification to the web interface.

        Args:
            message: Notification message text.
            color: Bulma color class (primary, warning, success, danger).
        """
        # Color should be bulma compatible: primary, warning, success, danger
        hide_notifications = self.preferences.get_or_default("hide_notifications")
        if not hide_notifications:
            # don't allow new messages to clobber existing commands, one message at a time
            # other commands have a higher priority
            if self.now_playing_notification != None:
                return
            self.now_playing_notification = message + "::is-" + color
            # Emit notification via SocketIO for event-driven architecture
            self._emit("notification", self.now_playing_notification, namespace="/")

    def log_and_send(self, message: str, category: str = "info") -> None:
        """Log a message and send it as a notification.

        Args:
            message: Message to log and display.
            category: Message category (info, success, warning, danger).
        """
        # Category should be one of: info, success, warning, danger
        if category == "success":
            logging.info(message)
            self.send_notification(message, "success")
        elif category == "warning":
            logging.warning(message)
            self.send_notification(message, "warning")
        elif category == "danger":
            logging.error(message)
            self.send_notification(message, "danger")
        else:
            logging.info(message)
            self.send_notification(message, "primary")

    def transpose_current(self, semitones: int) -> None:
        """Restart the current song with a new transpose value.

        Args:
            semitones: Number of semitones to transpose.
        """
        filename = self.playback_controller.now_playing_filename
        user = self.playback_controller.now_playing_user
        now_playing = self.playback_controller.now_playing

        if filename is None or user is None:
            logging.warning("Cannot transpose: no song currently playing")
            return
        # MSG: Message shown after the song is transposed, first is the semitones and then the song name
        self.log_and_send(_("Transposing by %s semitones: %s") % (semitones, now_playing))
        # Insert the same song at the top of the queue with transposition
        self.queue_manager.enqueue(filename, user, semitones, True)
        self.playback_controller.skip(log_action=False)

    def volume_change(self, vol_level: float) -> bool:
        """Set the volume level.

        Args:
            vol_level: Volume level (0.0 to 1.0).

        Returns:
            True after setting volume.
        """
        self.volume = vol_level
        # MSG: Message shown after the volume is changed, will be followed by the volume level
        self.log_and_send(_("Volume: %s") % (int(self.volume * 100)))
        self.update_now_playing_socket()
        return True

    def vol_up(self) -> None:
        """Increase volume by 10%."""
        new_vol = min(self.volume + 0.1, 1.0)
        self.volume_change(new_vol)
        logging.debug(f"Increasing volume by 10%: {self.volume}")

    def vol_down(self) -> None:
        """Decrease volume by 10%."""
        new_vol = max(self.volume - 0.1, 0.0)
        self.volume_change(new_vol)
        logging.debug(f"Decreasing volume by 10%: {self.volume}")

    def restart(self) -> bool:
        """Restart the current song from the beginning.

        Returns:
            True if successful, False if nothing playing.
        """
        if self.playback_controller.is_playing:
            now_playing = self.playback_controller.now_playing
            logging.info("Restarting: " + (now_playing or "unknown song"))
            self.playback_controller.is_paused = False
            self.update_now_playing_socket()
            return True
        else:
            logging.warning("Tried to restart, but no file is playing!")
            return False

    def stop(self) -> None:
        """Stop the karaoke run loop and clean up subprocesses."""
        self.running = False
        self._stop_stem_splitter()

    def handle_run_loop(self) -> None:
        """Handle one iteration of the main run loop with a sleep interval."""
        time.sleep(self.loop_interval / 1000)

    def reset_now_playing_notification(self) -> None:
        """Clear the current notification."""
        self.now_playing_notification = None

    def _is_song_ready(self, song_path: str) -> bool:
        """Check if a song's stems are ready for playback.

        When the splitter is enabled, a song is only ready once all 6
        stems exist. This prevents playback before splitting completes.
        """
        if not self.stem_separation_enabled:
            return True
        basename = os.path.basename(song_path)
        stem_dir = os.path.join(self.download_path, STEMS_SUBDIR, basename)
        return os.path.isdir(stem_dir) and stems_complete(stem_dir)

    def reset_now_playing(self) -> None:
        """Reset all now playing state to defaults."""
        self.playback_controller.reset_now_playing()
        self.volume = self.preferences.get_or_default("volume")
        self.stem_mix = {s: 1.0 for s in ALL_STEM_NAMES}
        self._stem_url_cache = (None, None, None)
        self.update_now_playing_socket()

    def get_now_playing(self) -> dict[str, Any]:
        """Get the current playback state.

        Returns:
            Dictionary with now playing info, queue preview, and volume.
        """
        queue = self.queue_manager.queue
        downloads_status = self.download_manager.get_downloads_status()
        next_song = get_up_next_item(
            queue,
            downloads_status,
            lambda song_path: build_song_readiness(song_path, self.stem_separation_enabled),
        )

        # Get playback state from PlaybackController
        playback_state = self.playback_controller.get_now_playing()

        # Build stem URLs for the currently playing file (cached to avoid repeated stat calls)
        stem_urls = None
        stems_available = False
        stem_progress = None  # {ready: N, total: 6, error: bool}
        now_file = self.playback_controller.now_playing_filename
        if self.stem_separation_enabled and now_file:
            cache = getattr(self, "_stem_url_cache", (None, None, None))
            if cache[0] == now_file and cache[1] is not None:
                stems_available, stem_urls = cache[1], cache[2]
            else:
                stem_paths = self.get_stem_paths(now_file)
                if stem_paths:
                    stems_available = True
                    stem_urls = {name: f"/stems/current/{name}.m4a" for name in stem_paths}
                # Only cache when stems are fully available
                if stems_available:
                    self._stem_url_cache = (now_file, stems_available, stem_urls)

            # Report progress when stems aren't ready yet
            if not stems_available:
                basename = os.path.basename(now_file)
                stem_dir = os.path.join(
                    self.download_path,
                    STEMS_SUBDIR,
                    basename,
                )
                all_stems = list(STEM_NAMES) + list(VOCAL_SPLIT_STEMS)
                total = len(all_stems)
                ready = 0
                has_error = False
                if os.path.isdir(stem_dir):
                    has_error = os.path.isfile(
                        os.path.join(stem_dir, ".error"),
                    )
                    ready = sum(
                        1 for s in all_stems if os.path.isfile(os.path.join(stem_dir, f"{s}.m4a"))
                    )
                stem_progress = {
                    "ready": ready,
                    "total": total,
                    "error": has_error,
                }

        now_basename = os.path.basename(now_file) if now_file else None

        return {
            **playback_state,
            "now_playing_file": now_basename,
            "up_next": next_song["title"] if next_song else None,
            "next_user": next_song["user"] if next_song else None,
            "up_next_step": next_song["download"]["step"] if next_song else None,
            "up_next_detail": next_song["download"]["detail"] if next_song else None,
            "up_next_pending": next_song["download"]["pending"] if next_song else None,
            "volume": self.volume,
            "stem_separation_enabled": self.stem_separation_enabled,
            "stems_available": stems_available,
            "stem_urls": stem_urls,
            "stem_mix": self.stem_mix,
            "stem_progress": stem_progress,
            "boot_id": self.boot_id,
        }

    def _emit(self, event: str, data: Any = None, **kwargs) -> None:
        """Thread-safe SocketIO emit — works from both async and sync contexts.

        Never raises — safe to call from the blocking run loop thread.
        """
        if not self.socketio:
            return
        try:
            loop = asyncio.get_running_loop()
            # Already in async context — schedule directly
            asyncio.ensure_future(self.socketio.emit(event, data, **kwargs), loop=loop)
        except RuntimeError:
            # Called from sync thread (run loop) — schedule on main loop
            if self._loop and self._loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.socketio.emit(event, data, **kwargs), self._loop
                    )
                except Exception:
                    pass  # Best-effort emit

    def update_now_playing_socket(self) -> None:
        """Emit now_playing state change via SocketIO."""
        self._emit("now_playing", self.get_now_playing(), namespace="/")

    def run(self) -> None:
        """Main run loop - processes queue and plays songs.

        This method blocks until stop() is called or KeyboardInterrupt.
        """
        logging.debug("Starting TommysKaraoke run loop")
        logging.info(f"Connect the player host to: {self.url}/splash")
        self.running = True
        while self.running:
            try:
                # Clean up if playback ended but state wasn't reset
                if (
                    not self.playback_controller.is_playing
                    and self.playback_controller.now_playing is not None
                ):
                    self.reset_now_playing()

                # Start next song from queue if not currently playing
                if len(self.queue_manager.queue) > 0 and not self.playback_controller.is_playing:
                    self.reset_now_playing()
                    # Splash delay between songs
                    splash_delay = self.preferences.get_or_default("splash_delay")
                    i = 0
                    while i < (splash_delay * 1000):
                        self.handle_run_loop()
                        i += self.loop_interval

                    # Pop next ready song (skip songs still splitting stems)
                    song = self.queue_manager.pop_next(
                        ready_check=self._is_song_ready
                    )
                    if not song:
                        continue
                    result = self.playback_controller.play_file(
                        song["file"], song["user"], song["semitones"]
                    )

                    if not result.success and result.error:
                        self.log_and_send(result.error, "danger")

                self.playback_controller.log_output()
                self.handle_run_loop()
            except KeyboardInterrupt:
                logging.warning("Keyboard interrupt: Exiting tommyskaraoke...")
                self.running = False
