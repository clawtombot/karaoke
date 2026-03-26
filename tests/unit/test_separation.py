"""Unit tests for separation configuration helpers."""

import os

import pytest

from tommyskaraoke.lib.separation import build_model_cache_env, resolve_separation_config


class TestResolveSeparationConfig:
    """Tests for explicit separation config validation."""

    def test_returns_none_when_disabled(self):
        """Test that disabled separation returns no config."""
        assert (
            resolve_separation_config(
                enabled=False,
                backend=None,
                model=None,
                vocal_split_model=None,
                device=None,
                model_cache_dir=None,
            )
            is None
        )

    def test_requires_explicit_config_when_enabled(self):
        """Test that enabled separation fails without required config."""
        with pytest.raises(ValueError, match="missing required configuration"):
            resolve_separation_config(
                enabled=True,
                backend=None,
                model=None,
                vocal_split_model=None,
                device=None,
                model_cache_dir=None,
            )

    def test_requires_demucs_device(self):
        """Test that demucs needs an explicit cpu/cuda device."""
        with pytest.raises(ValueError, match="requires separation_device"):
            resolve_separation_config(
                enabled=True,
                backend="demucs",
                model="htdemucs_6s",
                vocal_split_model="UVR-BVE-4B_SN-44100-1.pth",
                device=None,
                model_cache_dir=None,
            )

    def test_accepts_explicit_demucs_cuda_config(self):
        """Test that a full demucs config is normalized."""
        config = resolve_separation_config(
            enabled=True,
            backend="demucs",
            model="htdemucs_6s",
            vocal_split_model="UVR-BVE-4B_SN-44100-1.pth",
            device="cuda",
            model_cache_dir="~/models",
        )

        assert config is not None
        assert config.backend == "demucs"
        assert config.model == "htdemucs_6s"
        assert config.vocal_split_model == "UVR-BVE-4B_SN-44100-1.pth"
        assert config.device == "cuda"
        assert config.model_cache_dir == os.path.abspath(os.path.expanduser("~/models"))


class TestBuildModelCacheEnv:
    """Tests for model cache environment wiring."""

    def test_builds_cache_env_paths(self):
        """Test that cache env vars point under the configured directory."""
        env = build_model_cache_env("~/models")
        base_dir = os.path.abspath(os.path.expanduser("~/models"))

        assert env == {
            "HF_HOME": os.path.join(base_dir, "huggingface"),
            "TORCH_HOME": os.path.join(base_dir, "torch"),
            "XDG_CACHE_HOME": base_dir,
        }
