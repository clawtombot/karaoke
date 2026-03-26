"""Tests for stem separation settings validation."""

from types import SimpleNamespace

import pytest

from tommyskaraoke.routes_fastapi.preferences import _preview_stem_separation_change


def make_karaoke_stub(**overrides):
    """Create a minimal karaoke-like object for preference validation tests."""
    values = {
        "stem_separation_enabled": False,
        "separation_backend": "",
        "separation_device": "",
        "separation_model": "",
        "vocal_split_model": "",
        "model_cache_dir": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_allows_incomplete_stem_settings_while_disabled():
    """Test that users can preconfigure settings before enabling the worker."""
    k = make_karaoke_stub(stem_separation_enabled=False)

    _preview_stem_separation_change(k, "separation_backend", "demucs")


def test_rejects_enabling_without_required_settings():
    """Test that enabling fails until backend and model choices are complete."""
    k = make_karaoke_stub(stem_separation_enabled=False)

    with pytest.raises(ValueError, match="missing required configuration"):
        _preview_stem_separation_change(k, "stem_separation_enabled", "true")


def test_accepts_complete_demucs_configuration():
    """Test that a complete persisted demucs config validates cleanly."""
    k = make_karaoke_stub(
        stem_separation_enabled=False,
        separation_backend="demucs",
        separation_device="cuda",
        separation_model="htdemucs_6s",
        vocal_split_model="UVR-BVE-4B_SN-44100-1.pth",
    )

    _preview_stem_separation_change(k, "stem_separation_enabled", "true")
