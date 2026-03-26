"""Simple JSON file cache for lyrics data."""

import hashlib
import json
import logging
import os

from tommyskaraoke.lib.lyrics.models import LyricsLine, LyricsWord, SongLyrics


class LyricsCache:
    """File-based lyrics cache using JSON serialization.

    Each cached entry is stored as a JSON file named by the MD5 hash of
    the normalized "title|artist" key.
    """

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _key_path(self, title: str, artist: str) -> str:
        """Generate the cache file path for a title/artist pair."""
        normalized = f"{title}|{artist}".lower().strip()
        h = hashlib.md5(normalized.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.json")

    def get(self, title: str, artist: str) -> SongLyrics | None:
        """Retrieve cached lyrics for a title/artist pair.

        Returns None on cache miss or corrupted data.
        """
        path = self._key_path(title, artist)
        if not os.path.isfile(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _deserialize(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logging.warning("Lyrics cache read failed for %s - %s: %s", title, artist, e)
            return None

    def put(self, title: str, artist: str, lyrics: SongLyrics) -> None:
        """Cache lyrics for a title/artist pair."""
        path = self._key_path(title, artist)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(lyrics.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logging.warning("Lyrics cache write failed for %s - %s: %s", title, artist, e)

    def has(self, title: str, artist: str) -> bool:
        """Check if lyrics are cached for a title/artist pair."""
        return os.path.isfile(self._key_path(title, artist))


def _deserialize(data: dict) -> SongLyrics:
    """Reconstruct a SongLyrics from its JSON representation."""
    lines: list[LyricsLine] = []
    for line_data in data.get("lines", []):
        words = [
            LyricsWord(start=w["start"], end=w["end"], text=w["text"])
            for w in line_data.get("words", [])
        ]
        lines.append(
            LyricsLine(
                start=line_data["start"],
                end=line_data["end"],
                text=line_data["text"],
                romanized=line_data.get("romanized"),
                translated=line_data.get("translated"),
                words=words,
            )
        )

    return SongLyrics(
        source=data.get("source", "cache"),
        language=data.get("language", ""),
        lines=lines,
        has_word_timing=data.get("has_word_timing", False),
        has_romanization=data.get("has_romanization", False),
        has_translation=data.get("has_translation", False),
    )
