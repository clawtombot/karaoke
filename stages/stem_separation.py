"""
Stage 1: Stem Separation
Uses audio-separator with BS-Roformer (best free/local SDR: 12.9 dB).
Produces vocals.wav and instrumental.wav in the job tmp directory.
"""

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("STEM_MODEL", "model_bs_roformer_ep_317_sdr_12.9755.ckpt")


def run(input_path: str, tmp_dir: str) -> dict:
    """
    Separate vocals and instrumental from input audio.

    Args:
        input_path: Path to input audio file (mp3, wav, flac, etc.)
        tmp_dir: Directory for intermediate files

    Returns:
        dict with keys 'vocals' and 'instrumental' (absolute paths)
    """
    from audio_separator.separator import Separator

    input_path = Path(input_path).resolve()
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Stem separation: {input_path.name} → {tmp_dir}")

    sep = Separator(output_dir=str(tmp_dir))
    sep.load_model(MODEL_NAME)
    output_files = sep.separate(str(input_path))

    # audio-separator names outputs: {stem}_(Vocals).wav, {stem}_(Instrumental).wav
    vocals_path = None
    instrumental_path = None

    for f in output_files:
        f_path = Path(f)
        if "(Vocals)" in f_path.name:
            dest = tmp_dir / "vocals.wav"
            shutil.move(str(f_path), str(dest))
            vocals_path = str(dest)
        elif "(Instrumental)" in f_path.name:
            dest = tmp_dir / "instrumental.wav"
            shutil.move(str(f_path), str(dest))
            instrumental_path = str(dest)

    if not vocals_path or not instrumental_path:
        raise RuntimeError(
            f"Stem separation did not produce expected outputs. Got: {output_files}"
        )

    logger.info(f"Stem separation complete: vocals={vocals_path}, instrumental={instrumental_path}")
    return {"vocals": vocals_path, "instrumental": instrumental_path}
