"""DNN-based vocal splitter worker for PiKaraoke.

Runs as a background subprocess, polling the main Flask app for songs to
process. Produces instrumental (nonvocal) and vocal-only M4A tracks alongside
each downloaded song.

Modes:
  DNN  - tsurumeso's CascadedNet (PyTorch). GPU if available, CPU fallback.
  Stereo - L-R subtraction. No GPU, no PyTorch, weaker quality.

Output layout (relative to download_path):
  songs/
    song.webm               <- original
    nonvocal/song.webm.m4a  <- instrumental
    vocal/song.webm.m4a     <- vocals only
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_video_to_wav(input_path: str, output_path: str) -> bool:
    """Extract audio from video to WAV at 44100 Hz (required by the DNN model)."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-f", "wav", "-ar", "44100",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


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
# Stereo subtraction (no ML deps required)
# ---------------------------------------------------------------------------

def split_stereo(in_wav: str, out_nonvocal_wav: Optional[str], out_vocal_wav: Optional[str]) -> bool:
    """Simple L-R stereo subtraction. Works without PyTorch."""
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
# DNN separation
# ---------------------------------------------------------------------------

class _Separator:
    """Thin wrapper around CascadedNet for inference."""

    def __init__(self, model, device, batchsize: int = 4, cropsize: int = 256, postprocess: bool = False):
        self.model = model
        self.offset = model.offset
        self.device = device
        self.batchsize = batchsize
        self.cropsize = cropsize
        self.postprocess = postprocess

    def _postprocess(self, X_spec, mask):
        if self.postprocess:
            from pikaraoke.lib import spec_utils
            import numpy as np
            mask_mag = np.abs(mask)
            mask_mag = spec_utils.merge_artifacts(mask_mag)
            mask = mask_mag * np.exp(1.j * np.angle(mask))
        y_spec = X_spec * mask
        v_spec = X_spec - y_spec
        return y_spec, v_spec

    def _infer(self, X_spec_pad, roi_size):
        import numpy as np
        import torch
        from pikaraoke.lib import dataset

        X_dataset = []
        patches = (X_spec_pad.shape[2] - 2 * self.offset) // roi_size
        for i in range(patches):
            start = i * roi_size
            X_dataset.append(X_spec_pad[:, :, start : start + self.cropsize])
        X_dataset = np.asarray(X_dataset)

        self.model.eval()
        mask_list = []
        with torch.no_grad():
            for i in range(0, patches, self.batchsize):
                batch = torch.from_numpy(X_dataset[i : i + self.batchsize]).to(self.device)
                mask = self.model.predict_mask(batch)
                mask_list.append(mask.detach().cpu().numpy())
        # Concatenate all batches (may differ in axis 0 size), then merge patches
        all_masks = np.concatenate(mask_list, axis=0)
        return np.concatenate(list(all_masks), axis=2)

    def separate(self, X_spec):
        import numpy as np
        from pikaraoke.lib import dataset

        n_frame = X_spec.shape[2]
        pad_l, pad_r, roi_size = dataset.make_padding(n_frame, self.cropsize, self.offset)
        X_pad = np.pad(X_spec, ((0, 0), (0, 0), (pad_l, pad_r)), mode="constant")
        X_pad /= np.abs(X_spec).max()
        mask = self._infer(X_pad, roi_size)[:, :, :n_frame]
        return self._postprocess(X_spec, mask)

    def separate_tta(self, X_spec):
        import numpy as np
        from pikaraoke.lib import dataset

        n_frame = X_spec.shape[2]
        pad_l, pad_r, roi_size = dataset.make_padding(n_frame, self.cropsize, self.offset)

        X_pad = np.pad(X_spec, ((0, 0), (0, 0), (pad_l, pad_r)), mode="constant")
        X_pad /= X_pad.max()
        mask = self._infer(X_pad, roi_size)

        pad_l2 = pad_l + roi_size // 2
        pad_r2 = pad_r + roi_size // 2
        X_pad2 = np.pad(X_spec, ((0, 0), (0, 0), (pad_l2, pad_r2)), mode="constant")
        X_pad2 /= X_pad2.max()
        mask_tta = self._infer(X_pad2, roi_size)[:, :, roi_size // 2 :]

        mask = (mask[:, :, :n_frame] + mask_tta[:, :, :n_frame]) * 0.5
        return self._postprocess(X_spec, mask)


def split_dnn(
    in_wav: str,
    out_nonvocal_wav: str,
    out_vocal_wav: Optional[str],
    model,
    device,
    batchsize: int = 4,
    cropsize: int = 256,
    tta: bool = False,
    postprocess: bool = False,
) -> bool:
    """Separate vocals from an audio file using the DNN model."""
    try:
        import numpy as np
        import librosa
        import soundfile as sf
        from pikaraoke.lib import spec_utils

        logger.info("Loading audio: %s", in_wav)
        X, sr = librosa.load(in_wav, sr=44100, mono=False, dtype=np.float32, res_type="kaiser_fast")
        if X.ndim == 1:
            X = np.stack([X, X])

        logger.info("Computing STFT ...")
        X_spec = spec_utils.wave_to_spectrogram(X, hop_length=1024, n_fft=2048)

        sep = _Separator(model, device, batchsize=batchsize, cropsize=cropsize, postprocess=postprocess)
        if tta:
            y_spec, v_spec = sep.separate_tta(X_spec)
        else:
            y_spec, v_spec = sep.separate(X_spec)

        logger.info("Writing instrumental track ...")
        wave = spec_utils.spectrogram_to_wave(y_spec, hop_length=1024)
        sf.write(out_nonvocal_wav, wave.T, sr)

        if out_vocal_wav:
            logger.info("Writing vocal track ...")
            wave = spec_utils.spectrogram_to_wave(v_spec, hop_length=1024)
            sf.write(out_vocal_wav, wave.T, sr)

        return True
    except Exception as e:
        logger.error("DNN split failed: %s", e, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def load_model(model_path: str, gpu: Optional[int] = None):
    """Load CascadedNet and auto-select device.

    Args:
        model_path: Path to baseline.pth weights file.
        gpu: CUDA device index. None = auto, -1 = force CPU.

    Returns:
        Tuple of (model, device). Returns (None, None) if torch unavailable.
    """
    try:
        import torch
        from pikaraoke.lib import nets

        device = torch.device("cpu")
        model = nets.CascadedNet(2048, 1024, 32, 128, True)
        model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()

        if gpu != -1 and torch.cuda.is_available():
            idx = 0 if gpu is None else gpu
            device = torch.device(f"cuda:{idx}")
            model.to(device)
            logger.info("Vocal splitter: using CUDA device %s", idx)
        else:
            logger.info("Vocal splitter: using CPU")

        return model, device
    except ImportError:
        logger.warning("PyTorch not installed — DNN vocal splitting unavailable. Falling back to stereo subtraction.")
        return None, None
    except Exception as e:
        logger.error("Failed to load vocal splitter model: %s", e)
        return None, None


# ---------------------------------------------------------------------------
# Worker loop (runs as a subprocess)
# ---------------------------------------------------------------------------

def _get_pending_songs(download_path: str, use_dnn: bool) -> list[str]:
    """Return basenames of songs not yet processed."""
    prefix = "" if use_dnn else "."
    nonvocal_dir = os.path.join(download_path, "nonvocal")
    vocal_dir = os.path.join(download_path, "vocal")
    pending = []

    if not os.path.isdir(nonvocal_dir) and not os.path.isdir(vocal_dir):
        return []

    for bn in os.listdir(download_path):
        if bn.startswith(".") or not os.path.isfile(os.path.join(download_path, bn)):
            continue
        needs_nonvocal = os.path.isdir(nonvocal_dir) and not os.path.isfile(
            os.path.join(nonvocal_dir, prefix + bn + ".m4a")
        )
        needs_vocal = os.path.isdir(vocal_dir) and not os.path.isfile(
            os.path.join(vocal_dir, prefix + bn + ".m4a")
        )
        if needs_nonvocal or needs_vocal:
            pending.append(bn)
    return pending


def run_worker(
    download_path: str,
    model_path: str,
    gpu: Optional[int] = None,
    batchsize: int = 4,
    cropsize: int = 256,
    tta: bool = False,
    postprocess: bool = False,
    ramdir: Optional[str] = None,
    poll_url: Optional[str] = None,
) -> None:
    """Main worker loop. Runs forever, processing songs as they appear.

    Args:
        download_path: Directory containing downloaded songs.
        model_path: Path to baseline.pth.
        gpu: CUDA device index (None=auto, -1=CPU).
        batchsize: DNN inference batch size.
        cropsize: DNN crop size.
        tta: Use test-time augmentation for better quality (slower).
        postprocess: Apply artifact merging post-process.
        ramdir: Temp dir for intermediate WAV files (ramdisk for speed).
        poll_url: Optional Flask URL to fetch queue order from.
    """
    logging.basicConfig(level=logging.INFO, format="[vocal-splitter] %(levelname)s %(message)s")
    logger.info("Starting vocal splitter worker (download_path=%s)", download_path)

    model, device = load_model(model_path, gpu)
    use_dnn = model is not None

    if use_dnn:
        logger.info("DNN model loaded. Mode: DNN")
    else:
        logger.info("Mode: stereo subtraction (no PyTorch)")

    tmp_dir = ramdir if (ramdir and os.path.isdir(ramdir)) else download_path
    in_wav = os.path.join(tmp_dir, ".splitter_input.wav")
    out_nonvocal_wav = os.path.join(tmp_dir, ".splitter_nonvocal.wav")
    out_vocal_wav = os.path.join(tmp_dir, ".splitter_vocal.wav")

    nonvocal_dir = os.path.join(download_path, "nonvocal")
    vocal_dir = os.path.join(download_path, "vocal")

    while True:
        pending = _get_pending_songs(download_path, use_dnn)
        if not pending:
            time.sleep(3)
            continue

        bn = pending[0]
        src = os.path.join(download_path, bn)
        logger.info("Processing: %s", bn)

        # Step 1: extract audio to WAV
        if not _ffmpeg_video_to_wav(src, in_wav):
            logger.error("ffmpeg failed to extract audio from %s", bn)
            # Touch a sentinel so we don't retry forever
            _touch_sentinel(download_path, bn, use_dnn)
            continue

        # Step 2: separate
        prefix = "" if use_dnn else "."
        need_nonvocal = os.path.isdir(nonvocal_dir)
        need_vocal = os.path.isdir(vocal_dir)

        success = False
        if use_dnn:
            success = split_dnn(
                in_wav,
                out_nonvocal_wav if need_nonvocal else os.devnull,
                out_vocal_wav if need_vocal else None,
                model,
                device,
                batchsize=batchsize,
                cropsize=cropsize,
                tta=tta,
                postprocess=postprocess,
            )
        else:
            success = split_stereo(
                in_wav,
                out_nonvocal_wav if need_nonvocal else None,
                out_vocal_wav if need_vocal else None,
            )

        if not success:
            logger.error("Separation failed for %s", bn)
            _touch_sentinel(download_path, bn, use_dnn)
            continue

        # Step 3: encode to M4A and move into place
        out_name = prefix + bn + ".m4a"
        if need_nonvocal:
            dest = os.path.join(nonvocal_dir, out_name)
            tmp_m4a = os.path.join(tmp_dir, ".splitter_nonvocal.m4a")
            if _ffmpeg_wav_to_m4a(out_nonvocal_wav, tmp_m4a):
                shutil.move(tmp_m4a, dest)
                logger.info("Saved instrumental: %s", dest)
        if need_vocal:
            dest = os.path.join(vocal_dir, out_name)
            tmp_m4a = os.path.join(tmp_dir, ".splitter_vocal.m4a")
            if _ffmpeg_wav_to_m4a(out_vocal_wav, tmp_m4a):
                shutil.move(tmp_m4a, dest)
                logger.info("Saved vocals: %s", dest)

        # Cleanup temp WAVs
        for f in [in_wav, out_nonvocal_wav, out_vocal_wav]:
            if os.path.exists(f):
                os.remove(f)


def _touch_sentinel(download_path: str, bn: str, use_dnn: bool) -> None:
    """Create an empty marker file so we skip this song next iteration."""
    prefix = "" if use_dnn else "."
    for subdir in ["nonvocal", "vocal"]:
        d = os.path.join(download_path, subdir)
        if os.path.isdir(d):
            sentinel = os.path.join(d, prefix + bn + ".m4a.err")
            open(sentinel, "w").close()


# ---------------------------------------------------------------------------
# CLI entry point (when launched as subprocess)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="PiKaraoke vocal splitter worker")
    p.add_argument("--download-path", "-d", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--gpu", type=int, default=None)
    p.add_argument("--batchsize", type=int, default=4)
    p.add_argument("--cropsize", type=int, default=256)
    p.add_argument("--tta", action="store_true")
    p.add_argument("--postprocess", action="store_true")
    p.add_argument("--ramdir", default=None)
    args = p.parse_args()

    if args.model is None:
        base = os.path.dirname(os.path.dirname(__file__))
        args.model = os.path.join(base, "models", "baseline.pth")

    run_worker(
        download_path=args.download_path,
        model_path=args.model,
        gpu=args.gpu,
        batchsize=args.batchsize,
        cropsize=args.cropsize,
        tta=args.tta,
        postprocess=args.postprocess,
        ramdir=args.ramdir,
    )
