"""
Stage 2: Lyrics Timing
Strategy: LRCLib.net API first (free, no key, 3M+ synced tracks).
Fallback: WhisperX transcription against isolated vocal stem.
Produces lyrics.lrc in tmp_dir.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

LRCLIB_API = "https://lrclib.net/api/get"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")


def fetch_lrclib(title: str, artist: str) -> str | None:
    """Query LRCLib.net for synced lyrics. Returns LRC string or None."""
    params = urllib.parse.urlencode({
        "track_name": title,
        "artist_name": artist,
    })
    url = f"{LRCLIB_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PHANTOM-Karaoke/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read())
            synced = data.get("syncedLyrics")
            if synced:
                logger.info("LRCLib: synced lyrics found")
                return synced
            plain = data.get("plainLyrics")
            if plain:
                logger.warning("LRCLib: only plain (unsynced) lyrics found — falling back to WhisperX")
            return None
    except Exception as e:
        logger.warning(f"LRCLib fetch failed: {e}")
        return None


def transcribe_whisperx(vocals_path: str) -> str:
    """
    Transcribe vocals using WhisperX. Returns LRC-formatted string.
    Runs against isolated vocal stem for better accuracy.
    """
    import whisperx

    logger.info(f"WhisperX transcription: {vocals_path} (model={WHISPER_MODEL})")

    device = "cuda" if _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model(WHISPER_MODEL, device, compute_type=compute_type)
    audio = whisperx.load_audio(vocals_path)
    result = model.transcribe(audio, batch_size=16)

    # Align for word-level timestamps
    align_model, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, device,
        return_char_alignments=False
    )

    return _segments_to_lrc(result["segments"])


def _segments_to_lrc(segments: list) -> str:
    """Convert WhisperX segments to LRC format."""
    lines = []
    for seg in segments:
        start_ms = int(seg["start"] * 1000)
        minutes = start_ms // 60000
        seconds = (start_ms % 60000) / 1000
        timestamp = f"[{minutes:02d}:{seconds:05.2f}]"
        text = seg["text"].strip()
        if text:
            lines.append(f"{timestamp}{text}")
    return "\n".join(lines)


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def run(tmp_dir: str, title: str, artist: str) -> dict:
    """
    Fetch or transcribe lyrics. Writes lyrics.lrc to tmp_dir.

    Args:
        tmp_dir: Directory containing vocals.wav (from stem_separation stage)
        title: Song title for LRCLib lookup
        artist: Artist name for LRCLib lookup

    Returns:
        dict with key 'lrc_path' and 'source' ('lrclib' or 'whisperx')
    """
    tmp_dir = Path(tmp_dir)
    lrc_path = tmp_dir / "lyrics.lrc"

    # Try LRCLib first
    lrc_content = fetch_lrclib(title, artist)
    source = "lrclib"

    if not lrc_content:
        logger.info("LRCLib miss — running WhisperX against vocal stem")
        vocals_path = str(tmp_dir / "vocals.wav")
        if not Path(vocals_path).exists():
            raise FileNotFoundError(f"vocals.wav not found at {vocals_path}")
        lrc_content = transcribe_whisperx(vocals_path)
        source = "whisperx"

    lrc_path.write_text(lrc_content, encoding="utf-8")
    logger.info(f"Lyrics written: {lrc_path} (source={source})")

    return {"lrc_path": str(lrc_path), "source": source}
