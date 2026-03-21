"""Stem splitter worker for PiKaraoke.

Runs as a background subprocess, processing songs as they appear.
Uses demucs-mlx with htdemucs_6s for 6-stem Apple Silicon GPU-accelerated separation.

Output layout (relative to download_path):
  songs/
    song.mp4                     <- original
    stems/song.mp4/
      drums.m4a                  <- individual stems
      bass.m4a
      other.m4a
      vocals.m4a
      guitar.m4a
      piano.m4a
"""

import logging
import os
import subprocess
import time
from pathlib import Path

from pikaraoke.constants import STEM_NAMES, STEMS_SUBDIR, stems_complete

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_wav_to_m4a(input_path: str, output_path: str, bitrate: str = "128k") -> bool:
    """Encode a WAV file to AAC/M4A."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:a", "aac", "-b:a", bitrate,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Demucs-MLX 6-stem separation (Apple Silicon GPU via Metal/MLX)
# ---------------------------------------------------------------------------

def split_demucs_6s(input_path: str, stem_dir: str, separator) -> bool:
    """Separate audio into 6 stems using demucs-mlx htdemucs_6s."""
    try:
        import numpy as np
        import soundfile as sf

        logger.info("Running demucs-mlx 6-stem separation...")
        _, stems = separator.separate_audio_file(input_path)

        for name in STEM_NAMES:
            wav_path = os.path.join(stem_dir, f"{name}.wav")
            data = np.array(stems[name]).T
            sf.write(wav_path, data, 44100)
            logger.info("Wrote %s stem", name)

        return True
    except Exception as e:
        logger.error("Demucs 6-stem separation failed: %s", e, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def load_separator():
    """Load demucs-mlx htdemucs_6s separator for Apple Silicon."""
    try:
        from demucs_mlx import Separator
        sep = Separator(model="htdemucs_6s")
        logger.info("Demucs-MLX htdemucs_6s loaded (Apple Silicon GPU via Metal)")
        return sep
    except ImportError:
        logger.error("demucs-mlx not installed. Stem splitting requires demucs-mlx.")
        return None
    except Exception as e:
        logger.error("Failed to load demucs-mlx: %s", e)
        return None


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _get_pending_songs(download_path: str) -> list[str]:
    """Return basenames of songs not yet fully processed into stems."""
    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    pending = []

    for bn in os.listdir(download_path):
        if bn.startswith(".") or not os.path.isfile(os.path.join(download_path, bn)):
            continue

        stem_dir = os.path.join(stems_base, bn)

        if os.path.isfile(os.path.join(stem_dir, ".error")):
            continue

        if os.path.isdir(stem_dir) and stems_complete(stem_dir):
            continue

        pending.append(bn)

    return pending


def run_worker(download_path: str, **_kwargs) -> None:
    """Main worker loop. Processes songs into 6 stems as they appear."""
    logging.basicConfig(level=logging.INFO, format="[stem-splitter] %(levelname)s %(message)s")
    logger.info("Starting stem splitter worker (download_path=%s)", download_path)

    separator = load_separator()
    if separator is None:
        logger.error("Cannot start stem splitter: no separator available")
        return

    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    os.makedirs(stems_base, exist_ok=True)

    while True:
        pending = _get_pending_songs(download_path)
        if not pending:
            time.sleep(3)
            continue

        bn = pending[0]
        src = os.path.join(download_path, bn)
        stem_dir = os.path.join(stems_base, bn)
        os.makedirs(stem_dir, exist_ok=True)
        logger.info("Processing: %s", bn)

        success = split_demucs_6s(src, stem_dir, separator)

        if not success:
            logger.error("Separation failed for %s", bn)
            Path(stem_dir, ".error").touch()
            continue

        # Encode each WAV stem to M4A
        all_encoded = True
        for name in STEM_NAMES:
            wav_path = os.path.join(stem_dir, f"{name}.wav")
            m4a_path = os.path.join(stem_dir, f"{name}.m4a")
            if os.path.exists(wav_path):
                if _ffmpeg_wav_to_m4a(wav_path, m4a_path):
                    os.remove(wav_path)
                    logger.info("Encoded %s stem to M4A", name)
                else:
                    logger.error("Failed to encode %s to M4A", name)
                    all_encoded = False

        if not all_encoded:
            Path(stem_dir, ".error").touch()
        else:
            logger.info("All stems ready for: %s", bn)


# ---------------------------------------------------------------------------
# CLI entry point (when launched as subprocess)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="PiKaraoke stem splitter worker")
    p.add_argument("--download-path", "-d", required=True)
    args = p.parse_args()

    run_worker(download_path=args.download_path)
