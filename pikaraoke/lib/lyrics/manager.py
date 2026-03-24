"""Lyrics manager: orchestrates fetching from multiple sources."""

import logging
import os

from pikaraoke.lib.lyrics.cache import LyricsCache
from pikaraoke.lib.lyrics.lrc_parser import parse_lrc
from pikaraoke.lib.lyrics.models import SongLyrics
from pikaraoke.lib.lyrics.romanizer import detect_cjk_language, romanize
from pikaraoke.lib.lyrics.word_estimator import estimate_word_timing, is_cjk_text


class LyricsManager:
    """Fetches timed lyrics from multiple sources with caching.

    Source priority:
        1. Local cache
        2. Local .lrc file alongside the video
        3. NetEase Cloud Music
        4. LRCLIB

    After fetching, word-level timing is estimated if not already present,
    and CJK romanization is added when applicable.
    """

    def __init__(self, cache_dir: str, download_path: str):
        self.cache = LyricsCache(cache_dir)
        self.download_path = download_path

    async def get_lyrics(
        self,
        title: str,
        artist: str = "",
        file_path: str | None = None,
    ) -> SongLyrics | None:
        """Fetch lyrics for a song, trying sources in priority order.

        Args:
            title: Song title.
            artist: Artist name (optional, improves search accuracy).
            file_path: Path to the song file (used to find local .lrc files).

        Returns:
            SongLyrics with timing data, or None if no lyrics found.
        """
        # 1. Check cache
        cached = self.cache.get(title, artist)
        if cached is not None:
            logging.debug("Lyrics cache hit for %s - %s", title, artist)
            return cached

        # 2. Check local .lrc file alongside video
        lyrics = self._try_local_lrc(file_path)

        # 3. Try NetEase
        if lyrics is None:
            lyrics = await self._try_netease(title, artist)

        # 4. Try LRCLIB
        if lyrics is None:
            lyrics = await self._try_lrclib(title, artist)

        if lyrics is None:
            return None

        # 5. Estimate word timing only for sources with partial word data (YRC).
        # Line-synced sources (lrclib, netease LRC) stay line-level — estimated
        # word timing looks wrong because the distribution is artificial.
        if not lyrics.has_word_timing and any(line.words for line in lyrics.lines):
            self._add_word_timing(lyrics)

        # 6. Add romanization if CJK
        self._add_romanization(lyrics)

        # 7. Detect language if not set
        if not lyrics.language:
            lyrics.language = self._detect_language(lyrics)

        # 8. Cache and return
        self.cache.put(title, artist, lyrics)
        logging.info(
            "Lyrics fetched for %s - %s from %s (%d lines)",
            title,
            artist,
            lyrics.source,
            len(lyrics.lines),
        )
        return lyrics

    def _try_local_lrc(self, file_path: str | None) -> SongLyrics | None:
        """Look for a .lrc file next to the song file."""
        if not file_path:
            return None

        # Try same name with .lrc extension
        base, _ = os.path.splitext(file_path)
        lrc_path = base + ".lrc"

        if not os.path.isfile(lrc_path):
            return None

        try:
            with open(lrc_path, "r", encoding="utf-8") as f:
                lrc_text = f.read()

            lines = parse_lrc(lrc_text)
            if not lines:
                return None

            has_word_timing = any(line.words for line in lines)
            return SongLyrics(
                source="local",
                language="",
                lines=lines,
                has_word_timing=has_word_timing,
            )
        except OSError as e:
            logging.warning("Failed to read local LRC file %s: %s", lrc_path, e)
            return None

    async def _try_netease(self, title: str, artist: str) -> SongLyrics | None:
        """Search NetEase Cloud Music for lyrics."""
        try:
            from pikaraoke.lib.lyrics import netease

            query = f"{artist} {title}".strip()
            song_id = await netease.search_song(query)
            if song_id is None:
                return None
            return await netease.get_lyrics(song_id)
        except Exception as e:
            logging.warning("NetEase lyrics fetch failed: %s", e)
            return None

    async def _try_lrclib(self, title: str, artist: str) -> SongLyrics | None:
        """Search LRCLIB for lyrics."""
        try:
            from pikaraoke.lib.lyrics import lrclib

            return await lrclib.search_lyrics(title, artist)
        except Exception as e:
            logging.warning("LRCLIB lyrics fetch failed: %s", e)
            return None

    def _add_word_timing(self, lyrics: SongLyrics) -> None:
        """Estimate word-level timing for lines that lack it."""
        any_words = False
        for line in lyrics.lines:
            if not line.words:
                line.words = estimate_word_timing(line)
                if line.words:
                    any_words = True
            else:
                any_words = True
        lyrics.has_word_timing = any_words

    def _add_romanization(self, lyrics: SongLyrics) -> None:
        """Add romanization for CJK lines that don't already have it."""
        if lyrics.has_romanization:
            return

        any_romanized = False
        language = lyrics.language or ""

        for line in lyrics.lines:
            if line.romanized is not None:
                any_romanized = True
                continue
            if is_cjk_text(line.text):
                romanized = romanize(line.text, language)
                if romanized:
                    line.romanized = romanized
                    any_romanized = True

        lyrics.has_romanization = any_romanized

    def _detect_language(self, lyrics: SongLyrics) -> str:
        """Detect the predominant language from lyrics content."""
        # Sample a few lines to detect language
        sample_text = " ".join(line.text for line in lyrics.lines[:10])
        detected = detect_cjk_language(sample_text)
        return detected or "en"
