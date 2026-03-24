"""Parse NetEase's proprietary YRC (word-level timing) format.

YRC format encodes word-level timing for karaoke display:
    [lineStartMs,lineDurationMs](wordStartMs,wordDurationMs,0)word(nextStartMs,nextDurMs,0)word...

Example:
    [20570,1900](20570,360,0)字(20930,150,0)符(21080,200,0)示(21280,190,0)例
"""

import re

from pikaraoke.lib.lyrics.models import LyricsLine, LyricsWord

LINE_PATTERN = re.compile(r"^\[(\d+),(\d+)\](.*)$")
WORD_PATTERN = re.compile(r"(?:\[\d+,\d+\])?\((\d+),(\d+),\d+\)((?:.(?!\(\d+,\d+,\d+\)))*.)")

# Metadata prefixes that NetEase embeds as fake lyric lines (credits, not lyrics)
_METADATA_PREFIXES = ("作曲", "作词", "编曲", "制作", "混音", "录音", "母带", "出品", "监制", "策划")


def _is_metadata_line(text: str) -> bool:
    """Return True if the line is a metadata credit, not actual lyrics."""
    stripped = text.strip()
    return any(stripped.startswith(p) for p in _METADATA_PREFIXES)


def _clean_word(text: str) -> str:
    """Clean YRC word text artifacts.

    Strips trailing apostrophes that YRC uses as line-break markers
    (e.g. "give'" → "give", "trash'" → "trash") while preserving
    internal apostrophes in contractions (e.g. "don't", "That's").
    """
    if len(text) > 1 and text.endswith("'"):
        return text[:-1]
    return text


def parse_yrc(yrc_text: str) -> list[LyricsLine]:
    """Parse YRC text into a list of LyricsLine with word-level timing.

    Args:
        yrc_text: Raw YRC formatted lyrics text.

    Returns:
        List of LyricsLine objects with populated word timing.
    """
    lines: list[LyricsLine] = []

    for raw_line in yrc_text.strip().splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        line_match = LINE_PATTERN.match(raw_line)
        if not line_match:
            continue

        line_start = float(line_match.group(1))
        line_duration = float(line_match.group(2))
        word_section = line_match.group(3)

        words: list[LyricsWord] = []
        full_text_parts: list[str] = []

        for word_match in WORD_PATTERN.finditer(word_section):
            word_start = float(word_match.group(1))
            word_duration = float(word_match.group(2))
            word_text = _clean_word(word_match.group(3).strip())

            if not word_text:
                continue

            words.append(
                LyricsWord(
                    start=word_start,
                    end=word_start + word_duration,
                    text=word_text,
                )
            )
            full_text_parts.append(word_text)

        line_text = " ".join(full_text_parts)
        if not line_text.strip():
            continue

        if _is_metadata_line(line_text):
            continue

        lines.append(
            LyricsLine(
                start=line_start,
                end=line_start + line_duration,
                text=line_text,
                words=words,
            )
        )

    return lines
