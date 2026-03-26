"""Unit tests for args module."""

import pytest

from tommyskaraoke.lib.args import arg_path_parse, parse_tommyskaraoke_args, parse_volume


class TestArgPathParse:
    """Tests for the arg_path_parse function."""

    def test_string_passthrough(self):
        """Test that a string path is returned unchanged."""
        result = arg_path_parse("/home/user/songs")
        assert result == "/home/user/songs"

    def test_list_joined_with_spaces(self):
        """Test that a list of paths is joined with spaces."""
        result = arg_path_parse(["/home/user/my", "songs", "folder"])
        assert result == "/home/user/my songs folder"

    def test_none_returns_none(self):
        """Test that None input returns None."""
        result = arg_path_parse(None)
        assert result is None

    def test_single_item_list(self):
        """Test that a single-item list returns just the item."""
        result = arg_path_parse(["/home/user/songs"])
        assert result == "/home/user/songs"

    def test_empty_list(self):
        """Test that an empty list returns empty string."""
        result = arg_path_parse([])
        assert result == ""


class TestParseVolume:
    """Tests for the parse_volume function."""

    def test_valid_volume_string(self):
        """Test parsing a valid volume string."""
        result = parse_volume("0.5", "test volume")
        assert result == 0.5

    def test_valid_volume_float(self):
        """Test parsing a valid volume float."""
        result = parse_volume(0.75, "test volume")
        assert result == 0.75

    def test_volume_zero(self):
        """Test that zero volume is valid."""
        result = parse_volume("0", "test volume")
        assert result == 0.0

    def test_volume_one(self):
        """Test that volume of 1 is valid."""
        result = parse_volume("1", "test volume")
        assert result == 1.0

    def test_volume_above_one_resets_to_default(self, capsys):
        """Test that volume above 1 resets to default."""
        result = parse_volume("1.5", "test volume")
        assert result == 0.85  # default_volume
        captured = capsys.readouterr()
        assert "ERROR" in captured.out

    def test_volume_negative_resets_to_default(self, capsys):
        """Test that negative volume resets to default."""
        result = parse_volume("-0.5", "test volume")
        assert result == 0.85  # default_volume
        captured = capsys.readouterr()
        assert "ERROR" in captured.out

    def test_volume_decimal_precision(self):
        """Test that decimal precision is preserved."""
        result = parse_volume("0.333", "test volume")
        assert result == 0.333


class TestSplitterEnvConfig:
    """Tests for env-driven splitter configuration."""

    def test_splitter_defaults_to_disabled(self, monkeypatch):
        """Test that the splitter stays off without explicit config."""
        monkeypatch.delenv("TOMMYSKARAOKE_VOCAL_SPLITTER", raising=False)
        monkeypatch.delenv("TOMMYSKARAOKE_SEPARATION_BACKEND", raising=False)
        monkeypatch.delenv("TOMMYSKARAOKE_SEPARATION_DEVICE", raising=False)
        monkeypatch.delenv("TOMMYSKARAOKE_SEPARATION_MODEL", raising=False)
        monkeypatch.delenv("TOMMYSKARAOKE_VOCAL_SPLIT_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["tommyskaraoke"])

        args = parse_tommyskaraoke_args()

        assert args.vocal_splitter is False
        assert args.separation_backend is None
        assert args.separation_device is None
        assert args.separation_model is None
        assert args.vocal_split_model is None

    def test_splitter_reads_explicit_env_config(self, monkeypatch):
        """Test that splitter config can be supplied via env vars."""
        monkeypatch.setenv("TOMMYSKARAOKE_VOCAL_SPLITTER", "true")
        monkeypatch.setenv("TOMMYSKARAOKE_SEPARATION_BACKEND", "demucs")
        monkeypatch.setenv("TOMMYSKARAOKE_SEPARATION_DEVICE", "cuda")
        monkeypatch.setenv("TOMMYSKARAOKE_SEPARATION_MODEL", "htdemucs_6s")
        monkeypatch.setenv("TOMMYSKARAOKE_VOCAL_SPLIT_MODEL", "UVR-BVE-4B_SN-44100-1.pth")
        monkeypatch.setenv("TOMMYSKARAOKE_MODEL_CACHE_DIR", "~/models")
        monkeypatch.setattr("sys.argv", ["tommyskaraoke"])

        args = parse_tommyskaraoke_args()

        assert args.vocal_splitter is True
        assert args.separation_backend == "demucs"
        assert args.separation_device == "cuda"
        assert args.separation_model == "htdemucs_6s"
        assert args.vocal_split_model == "UVR-BVE-4B_SN-44100-1.pth"
        assert args.model_cache_dir == "~/models"
