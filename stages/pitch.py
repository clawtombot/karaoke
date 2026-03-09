"""
Stage 3: Pitch Extraction
Uses torchcrepe with Viterbi decoding against isolated vocal stem.
Pipeline:
  1. F0 time series (10ms hop, 50-1000 Hz)
  2. Short-window median filter (removes vibrato microvariation)
  3. Snap to nearest semitone
  4. Group consecutive identical MIDI notes → segments
  5. Output pitch_segments.json: list of {start_ms, end_ms, midi_note, note_name}
"""

import json
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

HOP_LENGTH_MS = int(os.getenv("PITCH_HOP_MS", "10"))
FMIN = float(os.getenv("PITCH_FMIN", "50"))
FMAX = float(os.getenv("PITCH_FMAX", "1000"))
MEDIAN_FILTER_MS = int(os.getenv("PITCH_MEDIAN_MS", "50"))  # vibrato filter window
PERIODICITY_THRESHOLD = float(os.getenv("PITCH_PERIODICITY", "0.4"))

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(midi: int) -> str:
    octave = (midi // 12) - 1
    name = NOTE_NAMES[midi % 12]
    return f"{name}{octave}"


def hz_to_midi(hz: float) -> int | None:
    """Convert Hz to nearest MIDI note. Returns None for silence/unvoiced."""
    if hz <= 0:
        return None
    import librosa
    midi_float = librosa.hz_to_midi(hz)
    return int(round(float(midi_float)))


def run(tmp_dir: str) -> dict:
    """
    Extract pitch from vocals.wav and write pitch_segments.json.

    Args:
        tmp_dir: Directory containing vocals.wav

    Returns:
        dict with key 'pitch_segments_path'
    """
    import torch
    import torchcrepe
    import librosa

    tmp_dir = Path(tmp_dir)
    vocals_path = tmp_dir / "vocals.wav"
    output_path = tmp_dir / "pitch_segments.json"

    if not vocals_path.exists():
        raise FileNotFoundError(f"vocals.wav not found: {vocals_path}")

    logger.info(f"Pitch extraction: {vocals_path}")

    # Load audio at 16kHz mono (torchcrepe requirement)
    audio, sr = librosa.load(str(vocals_path), sr=16000, mono=True)
    audio_tensor = torch.tensor(audio).unsqueeze(0)

    hop_samples = int(sr * HOP_LENGTH_MS / 1000)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"torchcrepe: device={device}, hop={HOP_LENGTH_MS}ms, fmin={FMIN}, fmax={FMAX}")

    pitch, periodicity = torchcrepe.predict(
        audio_tensor,
        sr,
        hop_length=hop_samples,
        fmin=FMIN,
        fmax=FMAX,
        model="full",
        return_periodicity=True,
        decoder=torchcrepe.decode.viterbi,
        device=device,
    )

    pitch_np = pitch.squeeze().numpy()        # shape: (T,)
    period_np = periodicity.squeeze().numpy() # shape: (T,)

    # Zero out unvoiced frames (low periodicity = silence/noise)
    pitch_np[period_np < PERIODICITY_THRESHOLD] = 0.0

    # Vibrato filter: short-window median to remove microvariation
    filter_frames = max(1, int(MEDIAN_FILTER_MS / HOP_LENGTH_MS))
    if filter_frames % 2 == 0:
        filter_frames += 1  # must be odd for symmetric median
    from scipy.ndimage import median_filter
    voiced_mask = pitch_np > 0
    if voiced_mask.any():
        # Apply median filter only to voiced frames to avoid edge contamination
        smoothed = median_filter(pitch_np, size=filter_frames)
        pitch_np[voiced_mask] = smoothed[voiced_mask]

    # Convert Hz → MIDI, group consecutive identical notes → segments
    segments = []
    current_midi = None
    current_start_frame = 0

    def flush_segment(midi_note, start_frame, end_frame):
        if midi_note is None:
            return
        start_ms = int(start_frame * HOP_LENGTH_MS)
        end_ms = int(end_frame * HOP_LENGTH_MS)
        if end_ms - start_ms < HOP_LENGTH_MS * 2:
            return  # skip sub-frame noise
        segments.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "midi_note": midi_note,
            "note_name": midi_to_note_name(midi_note),
        })

    for i, hz in enumerate(pitch_np):
        midi = hz_to_midi(float(hz)) if hz > 0 else None
        if midi != current_midi:
            flush_segment(current_midi, current_start_frame, i)
            current_midi = midi
            current_start_frame = i

    flush_segment(current_midi, current_start_frame, len(pitch_np))

    output_path.write_text(json.dumps(segments, indent=2), encoding="utf-8")
    logger.info(f"Pitch extraction complete: {len(segments)} segments → {output_path}")

    return {"pitch_segments_path": str(output_path)}
