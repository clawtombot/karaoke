"""NetEase Cloud Music API client for lyrics retrieval.

Uses the v1 API endpoint which returns YRC word-level timing when available,
with LRC as fallback. Translation and romanization metadata are merged in.
"""

import logging

import httpx

from pikaraoke.lib.lyrics.lrc_parser import parse_lrc
from pikaraoke.lib.lyrics.models import LyricsLine, SongLyrics
from pikaraoke.lib.lyrics.yrc_parser import parse_yrc

NETEASE_BASE = "https://music.163.com/api"
REQUEST_TIMEOUT = 10.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


async def search_song(query: str) -> int | None:
    """Search NetEase for a song and return its ID.

    Args:
        query: Search query (typically "artist title").

    Returns:
        NetEase song ID, or None if not found.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            resp = await client.get(
                f"{NETEASE_BASE}/search/get",
                params={"s": query, "type": 1, "limit": 5},
                headers={"User-Agent": USER_AGENT, "Referer": "https://music.163.com/"},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            result = data.get("result", {})
            songs = result.get("songs", [])
            if not songs:
                return None

            return songs[0].get("id")
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logging.warning("NetEase search failed: %s", e)
            return None


async def get_lyrics(song_id: int) -> SongLyrics | None:
    """Fetch lyrics by NetEase song ID.

    Uses the v1 endpoint which returns YRC word-level timing when available,
    falling back to standard LRC.

    Args:
        song_id: NetEase song ID.

    Returns:
        SongLyrics with parsed lines, or None if unavailable.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            resp = await client.get(
                f"{NETEASE_BASE}/song/lyric/v1",
                params={"id": song_id, "lv": -1, "tv": -1, "rv": -1, "yv": 1},
                headers={"User-Agent": USER_AGENT, "Referer": "https://music.163.com/"},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            return _parse_lyric_response(data)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logging.warning("NetEase lyrics fetch failed for song %d: %s", song_id, e)
            return None


def _parse_lyric_response(data: dict) -> SongLyrics | None:
    """Parse the NetEase /song/lyric/v1 response.

    Prefers YRC (word-level timing) when available, falls back to LRC.
    """
    # Try YRC first (word-level timing)
    yrc_data = data.get("yrc", {})
    yrc_text = yrc_data.get("lyric", "") if isinstance(yrc_data, dict) else ""

    if yrc_text:
        lines = parse_yrc(yrc_text)
        has_word_timing = bool(lines)
    else:
        lines = None
        has_word_timing = False

    # Fall back to LRC
    if not lines:
        lrc_data = data.get("lrc", {})
        lrc_text = lrc_data.get("lyric", "")
        if not lrc_text:
            return None
        lines = parse_lrc(lrc_text)
        has_word_timing = any(line.words for line in lines)

    if not lines:
        return None

    # Translation lyrics — skip Chinese translations for non-Chinese songs
    # (NetEase tlyric is always Chinese, which is noise for EN/KR/JP karaoke)
    tlyric_data = data.get("tlyric", {})
    tlyric_text = tlyric_data.get("lyric", "") if isinstance(tlyric_data, dict) else ""
    has_translation = False
    if tlyric_text:
        translation_lines = parse_lrc(tlyric_text)
        # Only merge if translation is useful (not Chinese translations of non-Chinese lyrics)
        main_is_cjk = any(_has_cjk(line.text) for line in lines[:5])
        trans_is_cjk = any(_has_cjk(tl.text) for tl in translation_lines[:5])
        if not trans_is_cjk or main_is_cjk:
            # Keep: translation is non-CJK, or main lyrics are CJK (translation may be helpful)
            has_translation = _merge_translations(lines, translation_lines)

    # Romanization (pinyin/romaji)
    romalrc_data = data.get("romalrc", {})
    romalrc_text = romalrc_data.get("lyric", "") if isinstance(romalrc_data, dict) else ""
    has_romanization = False
    if romalrc_text:
        roma_lines = parse_lrc(romalrc_text)
        has_romanization = _merge_romanization(lines, roma_lines)

    source = "netease-yrc" if yrc_text and has_word_timing else "netease"
    return SongLyrics(
        source=source,
        language="",
        lines=lines,
        has_word_timing=has_word_timing,
        has_romanization=has_romanization,
        has_translation=has_translation,
    )


def _has_cjk(text: str) -> bool:
    """Check if text contains Chinese/Japanese/Korean characters."""
    import re
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _merge_translations(
    lines: list[LyricsLine], translation_lines: list[LyricsLine]
) -> bool:
    """Merge translation lines into main lyrics by matching timestamps."""
    if not translation_lines:
        return False

    # Build a lookup by start time (with 100ms tolerance)
    trans_map: dict[int, str] = {}
    for tl in translation_lines:
        key = round(tl.start / 100)
        trans_map[key] = tl.text

    merged = False
    for line in lines:
        key = round(line.start / 100)
        trans_text = trans_map.get(key)
        if trans_text:
            line.translated = trans_text
            merged = True

    return merged


def _merge_romanization(
    lines: list[LyricsLine], roma_lines: list[LyricsLine]
) -> bool:
    """Merge romanization lines into main lyrics by matching timestamps."""
    if not roma_lines:
        return False

    roma_map: dict[int, str] = {}
    for rl in roma_lines:
        key = round(rl.start / 100)
        roma_map[key] = rl.text

    merged = False
    for line in lines:
        key = round(line.start / 100)
        roma_text = roma_map.get(key)
        if roma_text:
            line.romanized = roma_text
            merged = True

    return merged
