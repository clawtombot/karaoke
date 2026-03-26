"""Stem splitter worker for TommysKaraoke.

Runs as a background subprocess, processing songs as they appear.
The first pass performs configurable 6-stem separation via Demucs or Demucs-MLX,
then a second pass splits vocals into lead + backing using audio-separator.

Output layout (relative to download_path):
  songs/
    song.mp4                     <- original
    stems/song.mp4/
      drums.m4a                  <- individual stems
      bass.m4a
      other.m4a
      vocals.m4a                 <- combined vocals (kept for compat)
      guitar.m4a
      piano.m4a
      lead_vocals.m4a            <- second-pass split
      backing_vocals.m4a         <- second-pass split
      singer.json                <- gender classification
"""

import fcntl
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tommyskaraoke.constants import (
    ALL_STEM_NAMES,
    STEM_NAMES,
    STEMS_SUBDIR,
    VOCAL_SPLIT_MODELS,
    VOCAL_SPLIT_STEMS,
    demucs_complete,
    stems_complete,
)
from tommyskaraoke.lib.separation import SeparationConfig, apply_model_cache_env, build_model_cache_env, resolve_separation_config

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
# First-pass stem separation
# ---------------------------------------------------------------------------


def split_mlx_6s(input_path: str, stem_dir: str, separator) -> bool:
    """Separate audio into 6 stems using Demucs-MLX.

    Writes the vocals stem first so the vocal split second pass
    can start in parallel with encoding the other stems.
    """
    try:
        import numpy as np
        import soundfile as sf

        logger.info("Running demucs-mlx separation...")
        _, stems = separator.separate_audio_file(input_path)

        # Write vocals first (enables parallel vocal split)
        wav_path = os.path.join(stem_dir, "vocals.wav")
        data = np.array(stems["vocals"]).T
        sf.write(wav_path, data, 44100)
        logger.info("Wrote vocals stem (priority)")

        # Write remaining stems
        for name in STEM_NAMES:
            if name == "vocals":
                continue
            wav_path = os.path.join(stem_dir, f"{name}.wav")
            data = np.array(stems[name]).T
            sf.write(wav_path, data, 44100)
            logger.info("Wrote %s stem", name)

        return True
    except Exception as e:
        logger.error("Demucs 6-stem separation failed: %s", e, exc_info=True)
        return False


def split_demucs_cli(input_path: str, stem_dir: str, config: SeparationConfig) -> bool:
    """Separate audio with the official Demucs CLI on CPU or CUDA."""
    temp_out_dir = tempfile.mkdtemp(prefix="demucs-", dir=stem_dir)
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        config.model,
        "-o",
        temp_out_dir,
        "-d",
        config.device or "cpu",
        input_path,
    ]
    env = {**os.environ, **build_model_cache_env(config.model_cache_dir)}

    try:
        logger.info(
            "Running demucs separation (model=%s, device=%s)...",
            config.model,
            config.device,
        )
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            logger.error("Demucs CLI failed: %s", result.stderr.strip() or result.stdout.strip())
            return False

        model_dir = Path(temp_out_dir) / config.model
        source_dir = next(
            (
                candidate
                for candidate in model_dir.rglob("*")
                if candidate.is_dir() and all((candidate / f"{name}.wav").is_file() for name in STEM_NAMES)
            ),
            None,
        )
        if source_dir is None:
            logger.error("Demucs CLI output did not contain the expected 6-stem files")
            return False

        for name in STEM_NAMES:
            shutil.copy2(source_dir / f"{name}.wav", Path(stem_dir) / f"{name}.wav")
            logger.info("Copied %s stem from demucs output", name)

        return True
    except Exception as e:
        logger.error("Demucs CLI separation failed: %s", e, exc_info=True)
        return False
    finally:
        shutil.rmtree(temp_out_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Vocal split second pass (lead vs backing vocals)
# ---------------------------------------------------------------------------


def _run_vocal_split(vocals_path: str, stem_dir: str, model: str, model_cache_dir: str | None = None) -> bool:
    """Split a vocals stem into lead_vocals and backing_vocals using audio-separator.

    Returns True on success, False on failure.
    """
    try:
        apply_model_cache_env(model_cache_dir)
        from audio_separator.separator import Separator

        model_config = VOCAL_SPLIT_MODELS.get(model, {"swap": True})
        swap = model_config["swap"]
        separator_model_dir = None
        if model_cache_dir:
            separator_model_dir = os.path.join(model_cache_dir, "audio-separator")
            os.makedirs(separator_model_dir, exist_ok=True)

        logger.info("Running vocal split second pass with %s (swap=%s)...", model, swap)
        sep = Separator(
            output_dir=stem_dir,
            output_format="WAV",
            log_level=logging.WARNING,
            model_file_dir=separator_model_dir,
        )
        sep.load_model(model)
        output_files = sep.separate(vocals_path)

        # Rename outputs to standard names
        for f in output_files:
            basename = os.path.basename(f)
            full_path = os.path.join(stem_dir, basename) if not os.path.isabs(f) else f
            if "(Vocals)" in basename:
                # For BVE (swap=True): primary output = backing vocals
                # For HP-Karaoke (swap=False): primary output = lead vocals
                target = "backing_vocals.wav" if swap else "lead_vocals.wav"
                os.rename(full_path, os.path.join(stem_dir, target))
                logger.info("Renamed %s -> %s", basename, target)
            elif "(Instrumental)" in basename:
                target = "lead_vocals.wav" if swap else "backing_vocals.wav"
                os.rename(full_path, os.path.join(stem_dir, target))
                logger.info("Renamed %s -> %s", basename, target)

        return (
            os.path.isfile(os.path.join(stem_dir, "lead_vocals.wav"))
            and os.path.isfile(os.path.join(stem_dir, "backing_vocals.wav"))
        )

    except Exception as e:
        logger.error("Vocal split failed: %s", e, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Singer gender detection
# ---------------------------------------------------------------------------


def _detect_singer_info(stem_dir: str) -> None:
    """Create default singer.json for the frontend to use.

    Defaults to male=blue for lead, female=pink for backing.
    Users can override via the UI. Auto-detection of singing voice gender
    is unreliable (male tenors like Bruno Mars have F0 overlapping with
    female altos), so we provide sensible defaults instead.
    """
    singer_info = {"lead": "male", "backing": "female"}
    output_path = os.path.join(stem_dir, "singer.json")
    with open(output_path, "w") as f:
        json.dump(singer_info, f)
    logger.info("Saved default singer info: %s", singer_info)


# ---------------------------------------------------------------------------
# MLX model loader
# ---------------------------------------------------------------------------


def load_mlx_separator(model: str):
    """Load a demucs-mlx separator for Apple Silicon."""
    try:
        from demucs_mlx import Separator

        sep = Separator(model=model, batch_size=2)
        logger.info("Demucs-MLX %s loaded (batch_size=2, Apple Silicon GPU via Metal)", model)
        return sep
    except ImportError:
        logger.error("demucs-mlx not installed. Stem splitting requires demucs-mlx.")
        return None
    except Exception as e:
        logger.error("Failed to load demucs-mlx: %s", e)
        return None


def split_stems(input_path: str, stem_dir: str, config: SeparationConfig) -> bool:
    """Dispatch first-pass stem separation to the configured backend."""
    apply_model_cache_env(config.model_cache_dir)

    if config.backend == "mlx":
        separator = load_mlx_separator(config.model)
        if separator is None:
            logger.error("Cannot load demucs-mlx separator")
            return False
        return split_mlx_6s(input_path, stem_dir, separator)

    return split_demucs_cli(input_path, stem_dir, config)


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
    """Return basenames of songs not yet fully processed (demucs + vocal split)."""
    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    pending = []

    for bn in os.listdir(download_path):
        if bn.startswith(".") or not os.path.isfile(os.path.join(download_path, bn)):
            continue

        if _is_temp_file(bn):
            continue

        stem_dir = os.path.join(stems_base, bn)

        if os.path.isdir(stem_dir) and stems_complete(stem_dir):
            continue

        # Skip .error only if demucs itself failed (no stems at all).
        # If demucs is done but vocal split isn't, clear the stale .error
        # and allow retry — the error was from before vocal split existed.
        error_file = os.path.join(stem_dir, ".error")
        if os.path.isfile(error_file):
            if demucs_complete(stem_dir):
                os.remove(error_file)
            else:
                continue

        pending.append(bn)

    return pending


def _process_one(download_path: str, basename: str, config: SeparationConfig) -> bool:
    """Process a single song: demucs stems + vocal split + gender detection.

    Designed to run in a short-lived subprocess so all Metal/MLX GPU memory
    is fully released when the process exits.

    The vocal split runs in parallel with stem encoding for speed.

    Returns True on success, False on failure.
    """
    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    src = os.path.join(download_path, basename)
    stem_dir = os.path.join(stems_base, basename)
    os.makedirs(stem_dir, exist_ok=True)

    # Phase 1: Demucs separation (skip if already done)
    if not demucs_complete(stem_dir):
        if not os.path.isfile(src):
            logger.warning("Source file gone, skipping: %s", basename)
            return False

        success = split_stems(src, stem_dir, config)
        if not success:
            logger.error("Separation failed for %s", basename)
            Path(stem_dir, ".error").touch()
            return False

        # Start vocal split in parallel with stem encoding
        vocals_wav = os.path.join(stem_dir, "vocals.wav")
        vocal_split_future = None

        with ThreadPoolExecutor(max_workers=1) as executor:
            if os.path.exists(vocals_wav):
                vocal_split_future = executor.submit(
                    _run_vocal_split,
                    vocals_wav,
                    stem_dir,
                    config.vocal_split_model,
                    config.model_cache_dir,
                )

            # Encode all 6 demucs stems to M4A while vocal split runs
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

            # Wait for vocal split to complete
            if vocal_split_future:
                vocal_split_ok = vocal_split_future.result()
                if vocal_split_ok:
                    logger.info("Vocal split completed successfully")
                else:
                    logger.warning("Vocal split failed (non-fatal)")

        if not all_encoded:
            Path(stem_dir, ".error").touch()
            return False

    # Phase 2: Vocal split (for songs that already have demucs but no vocal split)
    vocal_split_needed = not all(
        os.path.isfile(os.path.join(stem_dir, f"{s}.m4a"))
        for s in VOCAL_SPLIT_STEMS
    )
    if vocal_split_needed:
        # Use vocals.m4a as input (demucs already done)
        vocals_input = os.path.join(stem_dir, "vocals.m4a")
        if os.path.isfile(vocals_input):
            ok = _run_vocal_split(
                vocals_input,
                stem_dir,
                config.vocal_split_model,
                config.model_cache_dir,
            )
            if not ok:
                logger.warning("Vocal split failed for existing song: %s", basename)
                Path(stem_dir, ".vocal_split_error").touch()

    # Phase 3: Encode vocal split WAVs to M4A
    for name in VOCAL_SPLIT_STEMS:
        wav_path = os.path.join(stem_dir, f"{name}.wav")
        m4a_path = os.path.join(stem_dir, f"{name}.m4a")
        if os.path.exists(wav_path):
            if _ffmpeg_wav_to_m4a(wav_path, m4a_path):
                os.remove(wav_path)
                logger.info("Encoded %s to M4A", name)
            else:
                logger.error("Failed to encode %s to M4A", name)

    # Phase 4: Singer gender detection
    singer_json = os.path.join(stem_dir, "singer.json")
    if not os.path.isfile(singer_json):
        _detect_singer_info(stem_dir)

    # Phase 5: Pitch extraction from lead AND backing vocals
    try:
        from tommyskaraoke.lib.pitch import extract_and_save
        from tommyskaraoke.lib.pitch.extractor import PITCH_SUBDIR

        pitch_dir = os.path.join(download_path, PITCH_SUBDIR)
        name_base = os.path.splitext(basename)[0]

        # Lead vocals pitch (main pitch graph)
        lead_m4a = os.path.join(stem_dir, "lead_vocals.m4a")
        pitch_source = lead_m4a if os.path.isfile(lead_m4a) else os.path.join(stem_dir, "vocals.m4a")
        if os.path.isfile(pitch_source):
            extract_and_save(pitch_source, pitch_dir, output_name=basename)

        # Backing vocals pitch (harmony line)
        backing_m4a = os.path.join(stem_dir, "backing_vocals.m4a")
        if os.path.isfile(backing_m4a):
            extract_and_save(backing_m4a, pitch_dir, output_name=f"{name_base}_backing")
    except Exception as e:
        logger.warning("Pitch extraction failed (non-fatal): %s", e)

    logger.info("All stems ready for: %s", basename)
    return True


def run_worker(download_path: str, config: SeparationConfig, **_kwargs) -> None:
    """Main worker loop. Polls for pending songs and spawns a subprocess per song.

    Each song is processed in its own subprocess so that Metal/MLX GPU memory
    is fully released when processing completes (the OS reclaims all memory
    when the child exits).

    Uses a lock file to ensure only one daemon runs per download_path.
    """
    logging.basicConfig(level=logging.INFO, format="[stem-splitter] %(levelname)s %(message)s")
    apply_model_cache_env(config.model_cache_dir)

    stems_base = os.path.join(download_path, STEMS_SUBDIR)
    os.makedirs(stems_base, exist_ok=True)

    # Acquire exclusive lock — prevents duplicate daemons after tommyskaraoke restarts
    lock_path = os.path.join(stems_base, ".worker.lock")
    lock_file = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.info("Another stem splitter already running for %s, exiting", download_path)
        lock_file.close()
        return

    lock_file.write(str(os.getpid()))
    lock_file.flush()
    logger.info(
        "Starting stem splitter worker (download_path=%s, backend=%s, model=%s, vocal_split_model=%s)",
        download_path,
        config.backend,
        config.model,
        config.vocal_split_model,
    )

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
                    "tommyskaraoke.lib.vocal_splitter",
                    "--download-path",
                    download_path,
                    "--separation-backend",
                    config.backend,
                    "--separation-model",
                    config.model,
                    "--vocal-split-model",
                    config.vocal_split_model,
                    "--process-one",
                    bn,
                ]
                + (["--separation-device", config.device] if config.device else [])
                + (["--model-cache-dir", config.model_cache_dir] if config.model_cache_dir else []),
                capture_output=False,
                env={**os.environ, **build_model_cache_env(config.model_cache_dir)},
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

    p = argparse.ArgumentParser(description="TommysKaraoke stem splitter worker")
    p.add_argument("--download-path", "-d", required=True)
    p.add_argument("--process-one", help="Process a single song and exit")
    p.add_argument("--separation-backend", choices=["demucs", "mlx"], required=True)
    p.add_argument("--separation-device", choices=["cpu", "cuda", "mps", "mlx"])
    p.add_argument("--separation-model", required=True)
    p.add_argument("--vocal-split-model", required=True, help="Model for lead/backing vocal split")
    p.add_argument("--model-cache-dir", help="Directory for downloaded model caches")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="[stem-splitter] %(levelname)s %(message)s")
    config = resolve_separation_config(
        enabled=True,
        backend=args.separation_backend,
        model=args.separation_model,
        vocal_split_model=args.vocal_split_model,
        device=args.separation_device,
        model_cache_dir=args.model_cache_dir,
    )

    if args.process_one:
        ok = _process_one(args.download_path, args.process_one, config)
        raise SystemExit(0 if ok else 1)
    else:
        run_worker(download_path=args.download_path, config=config)
