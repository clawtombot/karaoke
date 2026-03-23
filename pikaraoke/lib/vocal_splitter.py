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
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-c:a",
        "aac",
        "-b:a",
        bitrate,
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

        sep = Separator(model="htdemucs_6s", batch_size=2)
        logger.info("Demucs-MLX htdemucs_6s loaded (batch_size=2, Apple Silicon GPU via Metal)")
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


def _is_temp_file(basename: str) -> bool:
    """Return True if the file is a yt-dlp intermediate/temp file."""
    return (
        ".part" in basename
        or ".temp." in basename
        or ".f1" in basename  # format fragments like .f137.mp4, .f140.m4a
    )


def _get_pending_songs(download_path: str) -> list[str]:
    """Return basenames of songs not yet fully processed into stems."""
    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    pending = []

    for bn in os.listdir(download_path):
        if bn.startswith(".") or not os.path.isfile(os.path.join(download_path, bn)):
            continue

        if _is_temp_file(bn):
            continue

        stem_dir = os.path.join(stems_base, bn)

        if os.path.isfile(os.path.join(stem_dir, ".error")):
            continue

        if os.path.isdir(stem_dir) and stems_complete(stem_dir):
            continue

        pending.append(bn)

    return pending


def _process_one(download_path: str, basename: str) -> bool:
    """Process a single song: separate stems and encode to M4A.

    Designed to run in a short-lived subprocess so all Metal/MLX GPU memory
    is fully released when the process exits.

    Returns True on success, False on failure.
    """
    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    src = os.path.join(download_path, basename)
    stem_dir = os.path.join(stems_base, basename)
    os.makedirs(stem_dir, exist_ok=True)

    if not os.path.isfile(src):
        logger.warning("Source file gone, skipping: %s", basename)
        return False

    separator = load_separator()
    if separator is None:
        logger.error("Cannot load separator")
        return False

    success = split_demucs_6s(src, stem_dir, separator)
    if not success:
        logger.error("Separation failed for %s", basename)
        Path(stem_dir, ".error").touch()
        return False

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
        return False

    logger.info("All stems ready for: %s", basename)

    # Extract pitch data from vocals stem (non-blocking, best-effort)
    vocals_m4a = os.path.join(stem_dir, "vocals.m4a")
    if os.path.isfile(vocals_m4a):
        try:
            from pikaraoke.lib.pitch import extract_and_save
            from pikaraoke.lib.pitch.extractor import PITCH_SUBDIR

            pitch_dir = os.path.join(download_path, PITCH_SUBDIR)
            extract_and_save(vocals_m4a, pitch_dir)
        except Exception as e:
            logger.warning("Pitch extraction failed (non-fatal): %s", e)

    return True


def run_worker(download_path: str, **_kwargs) -> None:
    """Main worker loop. Polls for pending songs and spawns a subprocess per song.

    Each song is processed in its own subprocess so that Metal/MLX GPU memory
    is fully released when processing completes (the OS reclaims all memory
    when the child exits).
    """
    import sys

    logging.basicConfig(level=logging.INFO, format="[stem-splitter] %(levelname)s %(message)s")
    logger.info("Starting stem splitter worker (download_path=%s)", download_path)

    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    os.makedirs(stems_base, exist_ok=True)

    while True:
        try:
            pending = _get_pending_songs(download_path)
            if not pending:
                time.sleep(3)
                continue

            bn = pending[0]
            logger.info("Spawning subprocess for: %s", bn)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pikaraoke.lib.vocal_splitter",
                    "--download-path",
                    download_path,
                    "--process-one",
                    bn,
                ],
                capture_output=False,
            )

            if result.returncode != 0:
                logger.error("Subprocess failed (exit %d) for: %s", result.returncode, bn)
                stem_dir = os.path.join(stems_base, bn)
                os.makedirs(stem_dir, exist_ok=True)
                Path(stem_dir, ".error").touch()
        except Exception as e:
            logger.error("Worker error (will retry): %s", e, exc_info=True)
            time.sleep(5)


# ---------------------------------------------------------------------------
# CLI entry point (when launched as subprocess)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="PiKaraoke stem splitter worker")
    p.add_argument("--download-path", "-d", required=True)
    p.add_argument("--process-one", help="Process a single song and exit")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="[stem-splitter] %(levelname)s %(message)s")

    if args.process_one:
        ok = _process_one(args.download_path, args.process_one)
        raise SystemExit(0 if ok else 1)
    else:
        run_worker(download_path=args.download_path)
