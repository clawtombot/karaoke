"""Vocal splitter worker for PiKaraoke.

Runs as a background subprocess, processing songs as they appear.
Uses demucs-mlx for fast Apple Silicon GPU-accelerated separation,
with stereo subtraction as a fallback.

Output layout (relative to download_path):
  songs/
    song.mp4               <- original
    nonvocal/song.mp4.m4a  <- instrumental
    vocal/song.mp4.m4a     <- vocals only
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

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
# Demucs-MLX separation (Apple Silicon GPU via Metal/MLX)
# ---------------------------------------------------------------------------

def split_demucs(
    input_path: str,
    out_nonvocal_wav: str,
    out_vocal_wav: str | None,
    separator,
) -> bool:
    """Separate vocals using demucs-mlx (HTDemucs on Apple Silicon)."""
    try:
        import numpy as np
        import soundfile as sf

        logger.info("Running demucs-mlx separation...")
        _, stems = separator.separate_audio_file(input_path)

        # Instrumental = drums + bass + other (everything minus vocals)
        instrumental = np.array(stems["drums"] + stems["bass"] + stems["other"]).T
        sf.write(out_nonvocal_wav, instrumental, 44100)
        logger.info("Wrote instrumental track")

        if out_vocal_wav:
            vocals = np.array(stems["vocals"]).T
            sf.write(out_vocal_wav, vocals, 44100)
            logger.info("Wrote vocal track")

        return True
    except Exception as e:
        logger.error("Demucs separation failed: %s", e, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Stereo subtraction (no ML deps required)
# ---------------------------------------------------------------------------

def split_stereo(in_wav: str, out_nonvocal_wav: str | None, out_vocal_wav: str | None) -> bool:
    """Simple L-R stereo subtraction. Works without any ML framework."""
    try:
        import numpy as np
        import librosa
        import soundfile as sf

        X, sr = librosa.load(in_wav, sr=44100, mono=False, dtype=np.float32, res_type="kaiser_fast")
        if X.ndim < 2 or X.shape[0] < 2:
            logger.warning("Stereo subtraction requires stereo audio; skipping.")
            return False
        if out_nonvocal_wav:
            sf.write(out_nonvocal_wav, X[0] - X[1], sr)
        if out_vocal_wav:
            sf.write(out_vocal_wav, X[0] + X[1], sr)
        return True
    except Exception as e:
        logger.error("Stereo split failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def load_separator():
    """Load demucs-mlx separator for Apple Silicon, or return None for stereo fallback."""
    try:
        from demucs_mlx import Separator
        sep = Separator(model="htdemucs")
        logger.info("Demucs-MLX loaded (Apple Silicon GPU via Metal)")
        return sep
    except ImportError:
        logger.warning("demucs-mlx not installed. Falling back to stereo subtraction.")
        return None
    except Exception as e:
        logger.error("Failed to load demucs-mlx: %s", e)
        return None


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _get_pending_songs(download_path: str) -> list[str]:
    """Return basenames of songs not yet processed."""
    nonvocal_dir = os.path.join(download_path, "nonvocal")
    vocal_dir = os.path.join(download_path, "vocal")
    pending = []

    if not os.path.isdir(nonvocal_dir) and not os.path.isdir(vocal_dir):
        return []

    for bn in os.listdir(download_path):
        if bn.startswith(".") or not os.path.isfile(os.path.join(download_path, bn)):
            continue
        needs_nonvocal = os.path.isdir(nonvocal_dir) and not os.path.isfile(
            os.path.join(nonvocal_dir, bn + ".m4a")
        ) and not os.path.isfile(os.path.join(nonvocal_dir, bn + ".m4a.err"))
        needs_vocal = os.path.isdir(vocal_dir) and not os.path.isfile(
            os.path.join(vocal_dir, bn + ".m4a")
        ) and not os.path.isfile(os.path.join(vocal_dir, bn + ".m4a.err"))
        if needs_nonvocal or needs_vocal:
            pending.append(bn)
    return pending


def _touch_sentinel(download_path: str, bn: str) -> None:
    """Create an empty marker file so we skip this song next iteration."""
    for subdir in ["nonvocal", "vocal"]:
        d = os.path.join(download_path, subdir)
        if os.path.isdir(d):
            sentinel = os.path.join(d, bn + ".m4a.err")
            open(sentinel, "w").close()


def run_worker(download_path: str, **_kwargs) -> None:
    """Main worker loop. Processes songs as they appear."""
    logging.basicConfig(level=logging.INFO, format="[vocal-splitter] %(levelname)s %(message)s")
    logger.info("Starting vocal splitter worker (download_path=%s)", download_path)

    separator = load_separator()
    use_demucs = separator is not None

    nonvocal_dir = os.path.join(download_path, "nonvocal")
    vocal_dir = os.path.join(download_path, "vocal")
    tmp_dir = download_path

    while True:
        pending = _get_pending_songs(download_path)
        if not pending:
            time.sleep(3)
            continue

        bn = pending[0]
        src = os.path.join(download_path, bn)
        logger.info("Processing: %s", bn)

        need_nonvocal = os.path.isdir(nonvocal_dir)
        need_vocal = os.path.isdir(vocal_dir)
        out_nonvocal_wav = os.path.join(tmp_dir, ".splitter_nonvocal.wav")
        out_vocal_wav = os.path.join(tmp_dir, ".splitter_vocal.wav")

        success = False
        if use_demucs:
            # Demucs-MLX works directly on the video/audio file (no ffmpeg pre-step)
            success = split_demucs(
                src,
                out_nonvocal_wav if need_nonvocal else os.devnull,
                out_vocal_wav if need_vocal else None,
                separator,
            )
        else:
            # Stereo fallback needs WAV extraction first
            in_wav = os.path.join(tmp_dir, ".splitter_input.wav")
            cmd = ["ffmpeg", "-y", "-i", src, "-f", "wav", "-ar", "44100", in_wav]
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                success = split_stereo(
                    in_wav,
                    out_nonvocal_wav if need_nonvocal else None,
                    out_vocal_wav if need_vocal else None,
                )
            if os.path.exists(in_wav):
                os.remove(in_wav)

        if not success:
            logger.error("Separation failed for %s", bn)
            _touch_sentinel(download_path, bn)
            continue

        # Encode WAV to M4A and move into place
        if need_nonvocal and os.path.exists(out_nonvocal_wav):
            dest = os.path.join(nonvocal_dir, bn + ".m4a")
            tmp_m4a = os.path.join(tmp_dir, ".splitter_nonvocal.m4a")
            if _ffmpeg_wav_to_m4a(out_nonvocal_wav, tmp_m4a):
                shutil.move(tmp_m4a, dest)
                logger.info("Saved instrumental: %s", dest)
        if need_vocal and out_vocal_wav and os.path.exists(out_vocal_wav):
            dest = os.path.join(vocal_dir, bn + ".m4a")
            tmp_m4a = os.path.join(tmp_dir, ".splitter_vocal.m4a")
            if _ffmpeg_wav_to_m4a(out_vocal_wav, tmp_m4a):
                shutil.move(tmp_m4a, dest)
                logger.info("Saved vocals: %s", dest)

        # Cleanup temp WAVs
        for f in [out_nonvocal_wav, out_vocal_wav]:
            if f and os.path.exists(f):
                os.remove(f)


# ---------------------------------------------------------------------------
# CLI entry point (when launched as subprocess)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="PiKaraoke vocal splitter worker")
    p.add_argument("--download-path", "-d", required=True)
    # Legacy args (ignored, kept for backward compat with karaoke.py launch command)
    p.add_argument("--model", default=None)
    p.add_argument("--gpu", type=int, default=None)
    p.add_argument("--tta", action="store_true")
    args = p.parse_args()

    run_worker(download_path=args.download_path)
