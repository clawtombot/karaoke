"""Parse standard and enhanced LRC lyric formats.

Standard LRC:
    [mm:ss.xx]Lyric line text

Enhanced LRC with word timestamps:
    [mm:ss.xx]<mm:ss.xx>word1 <mm:ss.xx>word2
"""

import re

from pikaraoke.lib.lyrics.models import LyricsLine, LyricsWord

TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,3}):(\d{2})\.(\d{2,3})\]")
WORD_TIMESTAMP_PATTERN = re.compile(r"<(\d{1,3}):(\d{2})\.(\d{2,3})>")
METADATA_PATTERN = re.compile(r"^\[(?:ti|ar|al|au|by|offset|re|ve|length):")


def parse_timestamp(ts: str) -> float:
    """Convert a timestamp string to milliseconds.

    Args:
        ts: Timestamp in "mm:ss.xx" or "mm:ss.xxx" format (without brackets).

    Returns:
        Time in milliseconds.
    """
    match = re.match(r"(\d{1,3}):(\d{2})\.(\d{2,3})", ts)
    if not match:
        raise ValueError(f"Invalid timestamp format: {ts}")

    minutes = int(match.group(1))
    seconds = int(match.group(2))
    centis = match.group(3)

    # Handle both .xx (centiseconds) and .xxx (milliseconds)
    if len(centis) == 2:
        ms = int(centis) * 10
    else:
        ms = int(centis)

    return minutes * 60_000 + seconds * 1_000 + ms


def _parse_enhanced_words(text: str, line_start: float, line_end: float) -> list[LyricsWord]:
    """Parse enhanced LRC word timestamps from a line's text content.

    Args:
        text: Line text possibly containing <mm:ss.xx> word markers.
        line_start: Line start time in milliseconds.
        line_end: Line end time in milliseconds.

    Returns:
        List of LyricsWord with timing, or empty list if no word markers found.
    """
    markers = list(WORD_TIMESTAMP_PATTERN.finditer(text))
    if not markers:
        return []

    words: list[LyricsWord] = []
    clean_text = text

    for i, marker in enumerate(markers):
        word_start = parse_timestamp(marker.group(0).strip("<>"))

        # Word text is everything between this marker and the next marker (or end of line)
        text_start = marker.end()
        if i + 1 < len(markers):
            text_end = markers[i + 1].start()
        else:
            text_end = len(text)

        word_text = text[text_start:text_end].strip()
        if not word_text:
            continue

        # Word end is the next marker's start time, or the line end
        if i + 1 < len(markers):
            word_end = parse_timestamp(markers[i + 1].group(0).strip("<>"))
        else:
            word_end = line_end

        words.append(LyricsWord(start=word_start, end=word_end, text=word_text))

    return words


def parse_lrc(lrc_text: str) -> list[LyricsLine]:
    """Parse LRC text into a list of LyricsLine.

    Handles both standard and enhanced (word-level) LRC formats.

    Args:
        lrc_text: Raw LRC formatted lyrics text.

    Returns:
        List of LyricsLine objects sorted by start time.
    """
    lines: list[LyricsLine] = []

    for raw_line in lrc_text.strip().splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # Skip metadata tags
        if METADATA_PATTERN.match(raw_line):
            continue

        # Extract all timestamps from the line (LRC allows multiple timestamps per line)
        timestamps: list[float] = []
        for ts_match in TIMESTAMP_PATTERN.finditer(raw_line):
            ts_str = ts_match.group(0).strip("[]")
            timestamps.append(parse_timestamp(ts_str))

        if not timestamps:
            continue

        # Text is everything after the last timestamp tag
        last_ts_end = 0
        for ts_match in TIMESTAMP_PATTERN.finditer(raw_line):
            last_ts_end = ts_match.end()
        text = raw_line[last_ts_end:].strip()

        if not text:
            continue

        # Create a line for each timestamp (handles duplicate-timestamp lines)
        for ts in timestamps:
            lines.append(
                LyricsLine(
                    start=ts,
                    end=ts,  # Will be fixed up in the sorting pass
                    text=WORD_TIMESTAMP_PATTERN.sub("", text).strip(),
                )
            )

    # Sort by start time
    lines.sort(key=lambda l: l.start)

    # Fix up end times: each line ends when the next begins
    for i in range(len(lines) - 1):
        lines[i].end = lines[i + 1].start
    if lines:
        # Last line: estimate 5 seconds duration
        lines[-1].end = lines[-1].start + 5000

    # Parse enhanced word timestamps now that we have correct line end times
    for raw_line in lrc_text.strip().splitlines():
        raw_line = raw_line.strip()
        if not raw_line or METADATA_PATTERN.match(raw_line):
            continue

        ts_matches = list(TIMESTAMP_PATTERN.finditer(raw_line))
        if not ts_matches:
            continue

        ts_str = ts_matches[0].group(0).strip("[]")
        line_start = parse_timestamp(ts_str)
        last_ts_end_pos = ts_matches[-1].end()
        text = raw_line[last_ts_end_pos:]

        if "<" not in text:
            continue

        # Find the matching LyricsLine
        for line in lines:
            if abs(line.start - line_start) < 1:
                words = _parse_enhanced_words(text, line.start, line.end)
                if words:
                    line.words = words
                break

    return lines
