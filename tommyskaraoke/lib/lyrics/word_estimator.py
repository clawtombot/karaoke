"""Estimate word-level timing from line-level timing.

When YRC or enhanced LRC word timing is unavailable, this module distributes
a line's duration across its words or characters proportionally.
"""

from tommyskaraoke.lib.lyrics.models import LyricsLine, LyricsWord

# CJK Unicode ranges
_CJK_RANGES = [
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0xFF65, 0xFFDC),  # Halfwidth Katakana / Hangul
]


def is_cjk_char(char: str) -> bool:
    """Check if a character is CJK (Chinese/Japanese/Korean)."""
    cp = ord(char)
    return any(start <= cp <= end for start, end in _CJK_RANGES)


def is_cjk_text(text: str) -> bool:
    """Check if text is predominantly CJK characters."""
    if not text:
        return False
    cjk_count = sum(1 for ch in text if is_cjk_char(ch))
    alpha_count = sum(1 for ch in text if ch.isalpha())
    if alpha_count == 0:
        return False
    return cjk_count / alpha_count > 0.5


def estimate_word_timing(line: LyricsLine) -> list[LyricsWord]:
    """Distribute line duration across words or characters.

    For CJK text, each character is treated as one syllable with equal duration.
    For Latin text, words are split on spaces and duration is distributed
    proportionally by character count.

    Args:
        line: A LyricsLine with start/end but no word-level timing.

    Returns:
        List of LyricsWord with estimated timing.
    """
    text = line.text.strip()
    if not text:
        return []

    duration = line.end - line.start
    if duration <= 0:
        return [LyricsWord(start=line.start, end=line.end, text=text)]

    if is_cjk_text(text):
        return _estimate_cjk(text, line.start, duration)
    return _estimate_latin(text, line.start, duration)


def _estimate_cjk(text: str, start: float, duration: float) -> list[LyricsWord]:
    """Estimate timing for CJK text: one word per character, equal distribution."""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return []

    per_char = duration / len(chars)
    words: list[LyricsWord] = []
    current = start

    for ch in chars:
        words.append(
            LyricsWord(
                start=round(current, 1),
                end=round(current + per_char, 1),
                text=ch,
            )
        )
        current += per_char

    return words


def _estimate_latin(text: str, start: float, duration: float) -> list[LyricsWord]:
    """Estimate timing for Latin text: split on spaces, proportional by length."""
    parts = text.split()
    if not parts:
        return []

    total_chars = sum(len(p) for p in parts)
    if total_chars == 0:
        return []

    words: list[LyricsWord] = []
    current = start

    for part in parts:
        word_duration = duration * (len(part) / total_chars)
        words.append(
            LyricsWord(
                start=round(current, 1),
                end=round(current + word_duration, 1),
                text=part,
            )
        )
        current += word_duration

    return words
