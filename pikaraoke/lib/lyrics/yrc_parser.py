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
            word_text = word_match.group(3)

            words.append(
                LyricsWord(
                    start=word_start,
                    end=word_start + word_duration,
                    text=word_text,
                )
            )
            full_text_parts.append(word_text)

        line_text = "".join(full_text_parts)
        if not line_text.strip():
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
