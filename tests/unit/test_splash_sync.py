"""Tests for splash screen socket event sync — master election, position relay, registration.

Defines expected behavior for multi-splash scenarios to catch desync regressions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pikaraoke.routes_fastapi.socket_events import setup_socket_events


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_splash_state():
    """Reset module-level splash state between tests."""
    import pikaraoke.routes_fastapi.socket_events as mod

    mod.splash_connections.clear()
    mod.master_splash_id = None
    yield
    mod.splash_connections.clear()
    mod.master_splash_id = None


@pytest.fixture
def sio():
    """Create a mock AsyncServer with captured event handlers."""
    mock_sio = MagicMock()
    mock_sio.emit = AsyncMock()
    handlers = {}

    def on_decorator(event):
        def register(fn):
            handlers[event] = fn
            return fn

        return register

    mock_sio.on = on_decorator
    setup_socket_events(mock_sio)
    return mock_sio, handlers


@pytest.fixture
def karaoke_mock():
    """Mock get_karaoke() to return a mock Karaoke instance."""
    mock_k = MagicMock()
    mock_k.playback_controller = MagicMock()
    mock_k.playback_controller.now_playing_position = 0
    with patch("pikaraoke.routes_fastapi.socket_events.get_karaoke", return_value=mock_k):
        yield mock_k


class TestMasterElection:
    """First splash becomes master; subsequent become slaves."""

    def test_first_splash_becomes_master(self, sio, karaoke_mock):
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        mock_sio.emit.assert_called_with("splash_role", "master", room="sid-A")

    def test_second_splash_becomes_slave(self, sio, karaoke_mock):
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        mock_sio.emit.reset_mock()
        run(handlers["register_splash"]("sid-B"))
        mock_sio.emit.assert_called_with("splash_role", "slave", room="sid-B")

    def test_master_disconnect_promotes_slave(self, sio, karaoke_mock):
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        run(handlers["register_splash"]("sid-B"))
        mock_sio.emit.reset_mock()
        run(handlers["disconnect"]("sid-A"))
        mock_sio.emit.assert_called_with("splash_role", "master", room="sid-B")

    def test_non_splash_disconnect_ignored(self, sio, karaoke_mock):
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        mock_sio.emit.reset_mock()
        run(handlers["disconnect"]("sid-remote"))
        mock_sio.emit.assert_not_called()


class TestIdempotentRegistration:
    """Re-registering the same SID must preserve its master role.

    Bug: splash registered twice (onMount + on('connect') callback), causing
    the same SID to be demoted from master to slave on the second call.
    """

    def test_reregister_same_sid_stays_master(self, sio, karaoke_mock):
        """Re-registering the master SID must keep it as master, not demote to slave."""
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        mock_sio.emit.reset_mock()
        run(handlers["register_splash"]("sid-A"))
        mock_sio.emit.assert_called_with("splash_role", "master", room="sid-A")

    def test_reregister_slave_stays_slave(self, sio, karaoke_mock):
        """Re-registering a slave SID must keep it as slave."""
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-A"))
        run(handlers["register_splash"]("sid-B"))
        mock_sio.emit.reset_mock()
        run(handlers["register_splash"]("sid-B"))
        mock_sio.emit.assert_called_with("splash_role", "slave", room="sid-B")


class TestPositionRelay:
    """Only master's position updates are relayed to other clients."""

    def test_master_position_relayed(self, sio, karaoke_mock):
        """Position from master is broadcast to all other clients."""
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-master"))
        mock_sio.emit.reset_mock()
        run(handlers["playback_position"]("sid-master", 42.5))
        mock_sio.emit.assert_called_with("playback_position", 42.5, skip_sid="sid-master")
        assert karaoke_mock.playback_controller.now_playing_position == 42.5

    def test_slave_position_not_relayed(self, sio, karaoke_mock):
        """Position from slave must be ignored — only master is authoritative."""
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-master"))
        run(handlers["register_splash"]("sid-slave"))
        mock_sio.emit.reset_mock()
        run(handlers["playback_position"]("sid-slave", 99.0))
        mock_sio.emit.assert_not_called()
        assert karaoke_mock.playback_controller.now_playing_position != 99.0

    def test_position_from_non_splash_ignored(self, sio, karaoke_mock):
        """Position from a non-splash client (e.g. remote) must be ignored."""
        mock_sio, handlers = sio
        run(handlers["register_splash"]("sid-master"))
        mock_sio.emit.reset_mock()
        run(handlers["playback_position"]("sid-remote", 10.0))
        mock_sio.emit.assert_not_called()


class TestEndSong:
    """end_song socket event triggers proper backend cleanup."""

    def test_end_song_calls_controller(self, sio, karaoke_mock):
        """end_song event must forward reason to playback controller."""
        _, handlers = sio
        run(handlers["end_song"]("sid-master", "complete"))
        karaoke_mock.playback_controller.end_song.assert_called_once_with("complete")

    def test_end_song_from_any_client(self, sio, karaoke_mock):
        """end_song should work regardless of sender."""
        _, handlers = sio
        run(handlers["end_song"]("unknown-sid", "skip"))
        karaoke_mock.playback_controller.end_song.assert_called_once_with("skip")
