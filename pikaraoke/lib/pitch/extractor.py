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


def _smooth_pitch(notes: list[PitchNote], window_ms: float = 150) -> list[PitchNote]:
    """Median-filter pitch to collapse vibrato into the center note.

    Vibrato oscillates at 5-7 Hz (~150-200ms period). A time-based median
    window absorbs the oscillation while preserving real note transitions.
    Gaps in voiced frames are respected — smoothing doesn't cross silences.
    """
    if len(notes) < 3:
        return notes

    hz_arr = np.array([n.hz for n in notes])
    t_arr = np.array([n.t for n in notes])
    smoothed = np.copy(hz_arr)

    half_sec = window_ms / 2000  # half-window in seconds

    for i in range(len(hz_arr)):
        t_center = t_arr[i]
        lo = i
        while lo > 0 and (t_center - t_arr[lo - 1]) <= half_sec:
            lo -= 1
        hi = i + 1
        while hi < len(hz_arr) and (t_arr[hi] - t_center) <= half_sec:
            hi += 1
        if hi - lo >= 3:
            smoothed[i] = np.median(hz_arr[lo:hi])

    return [
        PitchNote(
            t=n.t,
            hz=round(float(smoothed[i]), 2),
            midi=round(69 + 12 * np.log2(float(smoothed[i]) / 440)),
            voiced=n.voiced,
        )
        for i, n in enumerate(notes)
    ]


def _pyin_chunk(
    y: np.ndarray, sr: int, hop_length: int, time_offset: float, global_rms_peak: float
) -> list[PitchNote]:
    """Run pyin + noise gate on a chunk of audio. Returns unsmoothed notes."""
    import librosa

    f0, voiced_flag, _ = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        hop_length=hop_length,
    )
    rms = librosa.feature.rms(y=y, frame_length=2 * hop_length, hop_length=hop_length)[0]
    rms_threshold = global_rms_peak * 0.05 if global_rms_peak > 0 else 0
    min_len = min(len(f0), len(rms))
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)

    notes = []
    for i in range(min_len):
        freq, voiced, t = f0[i], voiced_flag[i], times[i]
        if voiced and not np.isnan(freq) and rms[i] >= rms_threshold:
            midi = round(69 + 12 * np.log2(float(freq) / 440))
            notes.append(PitchNote(
                t=round(float(t + time_offset), 4),
                hz=round(float(freq), 2),
                midi=midi,
                voiced=True,
            ))
    return notes


def extract_pitch_pyin(
    audio_path: str, sr: int = 22050, hop_length: int = 512, output_path: str | None = None,
    chunk_seconds: float = 10.0,
) -> list[PitchNote]:
    """Extract pitch using librosa.pyin (CPU, no GPU needed).

    Processes audio in 10-second chunks and writes partial results to
    output_path after each chunk so the frontend can display notes
    progressively. The first chunk is available within ~2-3 seconds.
    """
    import librosa

    y, sr = librosa.load(audio_path, sr=sr)

    # Global RMS peak for consistent noise gate across chunks
    global_rms = librosa.feature.rms(y=y, frame_length=2 * hop_length, hop_length=hop_length)[0]
    global_rms_peak = float(np.max(global_rms)) if len(global_rms) > 0 else 0

    chunk_samples = int(chunk_seconds * sr)
    total_samples = len(y)
    all_notes: list[PitchNote] = []

    for start in range(0, total_samples, chunk_samples):
        chunk = y[start : start + chunk_samples]
        time_offset = start / sr
        chunk_notes = _pyin_chunk(chunk, sr, hop_length, time_offset, global_rms_peak)
        all_notes.extend(chunk_notes)

        # Write partial results so frontend can start displaying
        if output_path:
            smoothed = _smooth_pitch(all_notes)
            data = [{"t": n.t, "hz": n.hz, "midi": n.midi} for n in smoothed]
            with open(output_path, "w") as f:
                json.dump(data, f)

    return _smooth_pitch(all_notes)


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
        return _smooth_pitch(notes)

    except ImportError:
        logger.warning("torchcrepe not installed, falling back to pyin")
        return extract_pitch_pyin(audio_path)


def extract_and_save(audio_path: str, output_dir: str, use_crepe: bool = False, output_name: str | None = None) -> str:
    """Extract pitch and save as JSON. Returns the output path.

    Args:
        output_name: Base name for the output file (without extension).
                     Defaults to the audio file's stem if not provided.
    """
    if output_name:
        name_without_ext = os.path.splitext(output_name)[0]
    else:
        name_without_ext = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{name_without_ext}.json")

    done_marker = output_path + ".done"
    if os.path.exists(done_marker):
        logger.info("Pitch data already exists: %s", output_path)
        return output_path

    os.makedirs(output_dir, exist_ok=True)

    if use_crepe:
        notes = extract_pitch_crepe(audio_path)
    else:
        # Progressive: writes partial results after each 30s chunk
        notes = extract_pitch_pyin(audio_path, output_path=output_path)

    # Final write (ensures smoothed complete data; also covers crepe path)
    data = [{"t": n.t, "hz": n.hz, "midi": n.midi} for n in notes]
    with open(output_path, "w") as f:
        json.dump(data, f)

    # Mark complete so future runs skip re-extraction
    with open(output_path + ".done", "w") as f:
        f.write("")

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
