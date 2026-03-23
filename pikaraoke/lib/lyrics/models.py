"""Data models for timed lyrics."""

from dataclasses import dataclass, field


@dataclass
class LyricsWord:
    """A single word with timing information."""

    start: float  # milliseconds
    end: float  # milliseconds
    text: str


@dataclass
class LyricsLine:
    """A single lyrics line with optional word-level timing."""

    start: float  # milliseconds
    end: float  # milliseconds
    text: str
    romanized: str | None = None
    translated: str | None = None
    words: list[LyricsWord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for JSON API response."""
        result: dict = {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": [{"start": w.start, "end": w.end, "text": w.text} for w in self.words],
        }
        if self.romanized is not None:
            result["romanized"] = self.romanized
        if self.translated is not None:
            result["translated"] = self.translated
        return result


@dataclass
class SongLyrics:
    """Complete lyrics for a song from a specific source."""

    source: str  # "netease", "lrclib", "local", "youtube"
    language: str  # ISO 639-1
    lines: list[LyricsLine] = field(default_factory=list)
    has_word_timing: bool = False
    has_romanization: bool = False
    has_translation: bool = False

    def to_dict(self) -> dict:
        """Serialize for JSON API response."""
        return {
            "source": self.source,
            "language": self.language,
            "has_word_timing": self.has_word_timing,
            "has_romanization": self.has_romanization,
            "has_translation": self.has_translation,
            "lines": [line.to_dict() for line in self.lines],
        }
