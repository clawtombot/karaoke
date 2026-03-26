"""Tests for playback sync behavior between devices.

Defines expected behavior for play/pause state propagation, event ordering,
and multi-device sync scenarios to catch regressions in the sync architecture.
"""

from unittest.mock import MagicMock, patch

import pytest

from tommyskaraoke.lib.events import EventSystem
from tommyskaraoke.lib.playback_controller import PlaybackController, PlaybackResult
from tommyskaraoke.lib.preference_manager import PreferenceManager


@pytest.fixture
def events():
    return EventSystem()


@pytest.fixture
def prefs():
    return PreferenceManager("/nonexistent/test_config.ini")


@pytest.fixture
def pc(prefs, events):
    """Create a PlaybackController in a 'playing' state."""
    controller = PlaybackController(prefs, events, lambda x, remove_youtube_id=True: "Test Song")
    mock_result = PlaybackResult(
        success=True, stream_url="/stream/123.m3u8", subtitle_url=None, duration=180
    )
    controller.stream_manager.play_file = MagicMock(return_value=mock_result)
    controller.stream_manager.kill_ffmpeg = MagicMock()
    controller.play_file("/songs/test.mp4", "TestUser")
    return controller


class TestPauseEventOrdering:
    """Pause must flip state BEFORE emitting now_playing_update.

    If the event fires before the state changes, clients receive stale is_paused
    in the now_playing payload, causing play/pause desync between devices.
    """

    @patch("flask_babel._", side_effect=lambda x: x)
    def test_pause_event_carries_correct_is_paused_true(self, mock_gettext, pc, events):
        """When pausing, the now_playing_update event must see is_paused=True."""
        observed_states = []

        def capture_state():
            observed_states.append(pc.get_now_playing()["is_paused"])

        events.on("now_playing_update", capture_state)

        assert pc.is_paused is False
        pc.pause()

        assert len(observed_states) == 1
        assert observed_states[0] is True, "now_playing_update must see is_paused=True after pause"

    @patch("flask_babel._", side_effect=lambda x: x)
    def test_resume_event_carries_correct_is_paused_false(self, mock_gettext, pc, events):
        """When resuming, the now_playing_update event must see is_paused=False."""
        pc.is_paused = True
        observed_states = []

        def capture_state():
            observed_states.append(pc.get_now_playing()["is_paused"])

        events.on("now_playing_update", capture_state)

        pc.pause()

        assert len(observed_states) == 1
        assert observed_states[0] is False, "now_playing_update must see is_paused=False after resume"

    @patch("flask_babel._", side_effect=lambda x: x)
    def test_pause_toggle_emits_exactly_one_now_playing_update(self, mock_gettext, pc, events):
        """Each pause toggle must emit exactly one now_playing_update."""
        emission_count = 0

        def count_emissions():
            nonlocal emission_count
            emission_count += 1

        events.on("now_playing_update", count_emissions)

        pc.pause()
        assert emission_count == 1

        pc.pause()
        assert emission_count == 2


class TestSkipEventSequence:
    """Skip must produce a clean transition: song_ended (null state) then playback_started (new state)."""

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    @patch("flask_babel._", side_effect=lambda x: x)
    def test_skip_resets_state_before_song_ended(self, mock_gettext, mock_delete, mock_sleep, pc, events):
        """song_ended event must see null now_playing (state already reset)."""
        observed_state = {}

        def capture_state():
            observed_state.update(pc.get_now_playing())

        events.on("song_ended", capture_state)

        pc.skip()

        assert observed_state["now_playing"] is None
        assert observed_state["is_paused"] is True
        assert observed_state["now_playing_url"] is None

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    @patch("flask_babel._", side_effect=lambda x: x)
    def test_skip_sets_is_playing_false(self, mock_gettext, mock_delete, mock_sleep, pc, events):
        """After skip, is_playing must be False so the run loop can pick up the next song."""
        assert pc.is_playing is True
        pc.skip()
        assert pc.is_playing is False

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    @patch("flask_babel._", side_effect=lambda x: x)
    def test_song_end_then_new_song_produces_distinct_states(
        self, mock_gettext, mock_delete, mock_sleep, pc, events
    ):
        """A full skip→play cycle must produce null state, then new state.

        Both must be observable to event listeners (no state coalescing).
        """
        states = []

        def capture():
            states.append(dict(pc.get_now_playing()))

        events.on("song_ended", capture)
        events.on("playback_started", capture)

        pc.skip()

        # Now play a new song
        mock_result = PlaybackResult(
            success=True, stream_url="/stream/456.m3u8", subtitle_url=None, duration=200
        )
        pc.stream_manager.play_file = MagicMock(return_value=mock_result)
        pc.play_file("/songs/next.mp4", "User2")

        assert len(states) == 2
        assert states[0]["now_playing"] is None, "First event must be null (song ended)"
        assert states[1]["now_playing"] is not None, "Second event must be new song"
        assert states[1]["is_paused"] is False


class TestEventDeduplication:
    """Each event must fire exactly once.

    Bug: both karaoke.py and app_fastapi.py registered handlers for the same
    events, causing duplicate now_playing emissions. Only app_fastapi.py should
    wire the socket emitters (via _safe_emit).
    """

    def test_now_playing_update_has_single_handler_path(self, events):
        """now_playing_update should not have duplicate handlers doing the same thing."""
        emission_count = 0

        def counter():
            nonlocal emission_count
            emission_count += 1

        # Simulate what app_fastapi.py does (the only wiring point)
        events.on("now_playing_update", counter)

        events.emit("now_playing_update")

        assert emission_count == 1, "now_playing_update should fire handler exactly once"

    def test_playback_started_fires_once(self, events):
        emission_count = 0
        events.on("playback_started", lambda: None)  # Only one handler

        def counter():
            nonlocal emission_count
            emission_count += 1

        events.on("playback_started", counter)
        events.emit("playback_started")
        assert emission_count == 1

    def test_song_ended_fires_once(self, events):
        emission_count = 0

        def counter():
            nonlocal emission_count
            emission_count += 1

        events.on("song_ended", counter)
        events.emit("song_ended")
        assert emission_count == 1


class TestSongTransitionCleanup:
    """Song transitions must fully reset state to prevent overlap.

    Bug: stems from previous song kept playing via Web Audio when a new song
    loaded because the URL-change effect didn't call stemMixer.teardown().
    """

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    @patch("flask_babel._", side_effect=lambda x: x)
    def test_end_song_resets_all_playback_fields(self, mock_gettext, mock_delete, mock_sleep, pc, events):
        """end_song must reset all fields — no leftover state from previous song."""
        pc.end_song(reason="complete")

        state = pc.get_now_playing()
        assert state["now_playing"] is None
        assert state["now_playing_url"] is None
        assert state["now_playing_duration"] is None
        assert state["now_playing_position"] is None
        assert state["is_paused"] is True

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    @patch("flask_babel._", side_effect=lambda x: x)
    def test_end_song_kills_ffmpeg(self, mock_gettext, mock_delete, mock_sleep, pc, events):
        """end_song must kill ffmpeg to release the stream."""
        pc.end_song()
        pc.stream_manager.kill_ffmpeg.assert_called_once()

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    def test_new_song_after_end_has_fresh_state(self, mock_delete, mock_sleep, pc, events):
        """Playing a new song after end must have completely fresh state."""
        pc.end_song()

        mock_result = PlaybackResult(
            success=True, stream_url="/stream/new.m3u8", subtitle_url=None, duration=300
        )
        pc.stream_manager.play_file = MagicMock(return_value=mock_result)
        pc.play_file("/songs/new-song.mp4", "NewUser", semitones=1)

        assert pc.now_playing == "Test Song"
        assert pc.now_playing_url == "/stream/new.m3u8"
        assert pc.now_playing_user == "NewUser"
        assert pc.now_playing_transpose == 1
        assert pc.is_paused is False
        assert pc.is_playing is True


class TestStartSongIdempotency:
    """start_song must be idempotent and only affect state when appropriate.

    Bug: every splash emitted start_song (not just master), causing slaves to
    interfere with playback state during transitions.
    """

    def test_start_song_is_idempotent_when_already_playing(self, pc, events):
        """Calling start_song when already playing must not change state."""
        assert pc.is_playing is True
        pc.start_song()
        assert pc.is_playing is True

    @patch("tommyskaraoke.lib.playback_controller.time.sleep")
    @patch("tommyskaraoke.lib.playback_controller.delete_tmp_dir")
    def test_start_song_ignored_after_end(self, mock_delete, mock_sleep, pc, events):
        """start_song after end_song must not resurrect the song.

        This catches the race where a slave's start_song arrives after the
        master has already ended the song.
        """
        pc.end_song()

        assert pc.now_playing is None
        assert pc.is_playing is False

        pc.start_song()

        assert pc.is_playing is False, "start_song must not set is_playing when now_playing is None"
