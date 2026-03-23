"""CJK romanization with graceful fallback when libraries are not installed.

Supports Japanese (romaji via pykakasi), Chinese (pinyin via pypinyin),
and Korean (romanization via korean-romanizer). Each dependency is optional;
functions return None when the library is unavailable.
"""

import logging

from pikaraoke.lib.lyrics.word_estimator import is_cjk_text


def romanize_japanese(text: str) -> str | None:
    """Convert Japanese text to romaji using pykakasi.

    Returns None if pykakasi is not installed.
    """
    try:
        import pykakasi

        kakasi = pykakasi.kakasi()
        result = kakasi.convert(text)
        return " ".join(item["hepburn"] for item in result)
    except ImportError:
        return None
    except Exception as e:
        logging.warning("Japanese romanization failed: %s", e)
        return None


def romanize_chinese(text: str) -> str | None:
    """Convert Chinese text to pinyin with tone marks.

    Returns None if pypinyin is not installed.
    """
    try:
        from pypinyin import Style, pinyin

        result = pinyin(text, style=Style.TONE)
        return " ".join(p[0] for p in result)
    except ImportError:
        return None
    except Exception as e:
        logging.warning("Chinese romanization failed: %s", e)
        return None


def romanize_korean(text: str) -> str | None:
    """Convert Korean text to romanized form.

    Returns None if korean-romanizer is not installed.
    """
    try:
        from korean_romanizer.romanizer import Romanizer

        romanizer = Romanizer(text)
        return romanizer.romanize()
    except ImportError:
        return None
    except Exception as e:
        logging.warning("Korean romanization failed: %s", e)
        return None


def detect_cjk_language(text: str) -> str | None:
    """Detect which CJK language the text most likely is.

    Uses Unicode block heuristics: hiragana/katakana -> Japanese,
    hangul -> Korean, CJK ideographs without kana -> Chinese.

    Returns:
        ISO 639-1 code ("ja", "zh", "ko") or None if not CJK.
    """
    if not text:
        return None

    has_hiragana = False
    has_katakana = False
    has_hangul = False
    has_cjk_ideo = False

    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x309F:
            has_hiragana = True
        elif 0x30A0 <= cp <= 0x30FF:
            has_katakana = True
        elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
            has_hangul = True
        elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            has_cjk_ideo = True

    if has_hiragana or has_katakana:
        return "ja"
    if has_hangul:
        return "ko"
    if has_cjk_ideo:
        return "zh"
    return None


def romanize(text: str, language: str = "") -> str | None:
    """Romanize CJK text, auto-detecting language if not specified.

    Args:
        text: Text to romanize.
        language: ISO 639-1 language code. If empty, auto-detects from text.

    Returns:
        Romanized string, or None if romanization is unavailable.
    """
    if not is_cjk_text(text):
        return None

    if not language:
        language = detect_cjk_language(text) or ""

    if language == "ja":
        return romanize_japanese(text)
    if language == "zh":
        return romanize_chinese(text)
    if language == "ko":
        return romanize_korean(text)

    # Unknown CJK: try Japanese first (most common karaoke language), then Chinese
    result = romanize_japanese(text)
    if result is not None:
        return result
    return romanize_chinese(text)
