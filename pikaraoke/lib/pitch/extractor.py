"""Pitch extraction from vocal stems.

Uses librosa.pyin by default (CPU, no GPU required).
Optional torchcrepe backend for better accuracy on Apple Silicon (MPS).
"""

import json
import logging
import os

import numpy as np

from pikaraoke.lib.pitch.models import PitchNote

logger = logging.getLogger(__name__)

PITCH_SUBDIR = "pitch"  # sits alongside stems/ in download_path


def extract_pitch_pyin(audio_path: str, sr: int = 22050, hop_length: int = 512) -> list[PitchNote]:
    """Extract pitch using librosa.pyin (CPU, no GPU needed)."""
    import librosa

    y, sr = librosa.load(audio_path, sr=sr)
    f0, voiced_flag, _ = librosa.pyin(
        y,
        sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        hop_length=hop_length,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)

    notes = []
    for t, freq, voiced in zip(times, f0, voiced_flag):
        if voiced and not np.isnan(freq):
            midi = round(69 + 12 * np.log2(float(freq) / 440))
            notes.append(
                PitchNote(
                    t=round(float(t), 4),
                    hz=round(float(freq), 2),
                    midi=midi,
                    voiced=True,
                )
            )
    return notes


def extract_pitch_crepe(audio_path: str) -> list[PitchNote]:
    """Extract pitch using torchcrepe (GPU-accelerated on Apple Silicon MPS)."""
    try:
        import torch
        import torchcrepe

        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("torchcrepe using device: %s", device)

        import librosa

        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        audio = torch.tensor(y[None], dtype=torch.float32)

        # torchcrepe expects (batch, samples) at 16kHz
        hop_length = 160  # 10ms at 16kHz
        fmin = 32.70  # C1
        fmax = 2093.0  # C7

        pitch, periodicity = torchcrepe.predict(
            audio,
            sample_rate=16000,
            hop_length=hop_length,
            fmin=fmin,
            fmax=fmax,
            model="full",
            decoder=torchcrepe.decode.weighted_argmax,
            return_periodicity=True,
            device=device,
        )

        # pitch/periodicity shape: (1, frames)
        pitch_np = pitch.squeeze(0).cpu().numpy()
        periodicity_np = periodicity.squeeze(0).cpu().numpy()
        times = np.arange(len(pitch_np)) * (hop_length / 16000)

        VOICED_THRESHOLD = 0.5
        notes = []
        for t, freq, prob in zip(times, pitch_np, periodicity_np):
            voiced = bool(prob >= VOICED_THRESHOLD) and not np.isnan(freq) and freq > 0
            if voiced:
                midi = round(69 + 12 * np.log2(float(freq) / 440))
                notes.append(
                    PitchNote(
                        t=round(float(t), 4),
                        hz=round(float(freq), 2),
                        midi=midi,
                        voiced=True,
                    )
                )
        return notes

    except ImportError:
        logger.warning("torchcrepe not installed, falling back to pyin")
        return extract_pitch_pyin(audio_path)


def extract_and_save(audio_path: str, output_dir: str, use_crepe: bool = False) -> str:
    """Extract pitch and save as JSON. Returns the output path."""
    basename = os.path.basename(audio_path)
    name_without_ext = os.path.splitext(basename)[0]
    output_path = os.path.join(output_dir, f"{name_without_ext}.json")

    if os.path.exists(output_path):
        logger.info("Pitch data already exists: %s", output_path)
        return output_path

    os.makedirs(output_dir, exist_ok=True)

    if use_crepe:
        notes = extract_pitch_crepe(audio_path)
    else:
        notes = extract_pitch_pyin(audio_path)

    data = [{"t": n.t, "hz": n.hz, "midi": n.midi} for n in notes]

    with open(output_path, "w") as f:
        json.dump(data, f)

    logger.info("Saved pitch data (%d notes) to: %s", len(notes), output_path)
    return output_path


def get_pitch_data(download_path: str, song_basename: str) -> list[dict] | None:
    """Load precomputed pitch data for a song, if available."""
    pitch_dir = os.path.join(download_path, PITCH_SUBDIR)
    for name in [song_basename, os.path.splitext(song_basename)[0]]:
        json_path = os.path.join(pitch_dir, f"{name}.json")
        if os.path.isfile(json_path):
            with open(json_path) as f:
                return json.load(f)
    return None
