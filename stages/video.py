"""
Stage 4: Video Composition
Produces output.mp4 with:
  - Instrumental audio
  - Timed lyrics overlay (from LRC file)
  - JP-style pitch guide (scrolling horizontal bars from pitch_segments.json)

Pipeline:
  1. matplotlib renders pitch guide frames (image sequence)
  2. MoviePy composites pitch guide + lyrics text clips
  3. FFmpeg muxes instrumental audio + video → H.264 MP4

Time reference: sample count from original audio, not wall clock.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

FPS = int(os.getenv("VIDEO_FPS", "30"))
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))
PITCH_PANEL_HEIGHT = int(os.getenv("PITCH_PANEL_HEIGHT", "200"))  # px, bottom panel
FONT_SIZE = int(os.getenv("LYRIC_FONT_SIZE", "48"))

# Pitch guide scroll: how many ms of audio visible in the pitch panel at once
PITCH_WINDOW_MS = int(os.getenv("PITCH_WINDOW_MS", "4000"))

BG_COLOR = (10, 10, 20)       # dark navy background
LYRIC_COLOR = "white"
LYRIC_ACTIVE_COLOR = "#FFD700"  # gold for active line

# MIDI pitch range for color mapping (C3=48 to C6=84 spans typical vocal range)
MIDI_LOW = int(os.getenv("MIDI_COLOR_LOW", "48"))
MIDI_HIGH = int(os.getenv("MIDI_COLOR_HIGH", "84"))


def _parse_lrc(lrc_path: str) -> list[dict]:
    """Parse LRC file into list of {time_ms, text}."""
    import re
    lines = []
    pattern = re.compile(r"\[(\d+):(\d+\.\d+)\](.*)")
    with open(lrc_path, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                minutes, seconds, text = int(m.group(1)), float(m.group(2)), m.group(3).strip()
                time_ms = int(minutes * 60000 + seconds * 1000)
                if text:
                    lines.append({"time_ms": time_ms, "text": text})
    return sorted(lines, key=lambda x: x["time_ms"])


def _midi_to_color(midi_note: int) -> tuple:
    """Map MIDI note to BGR color (low=blue, mid=green, high=red)."""
    t = np.clip((midi_note - MIDI_LOW) / max(1, MIDI_HIGH - MIDI_LOW), 0, 1)
    r = int(t * 255)
    g = int((1 - abs(2 * t - 1)) * 200)
    b = int((1 - t) * 255)
    return (r / 255, g / 255, b / 255)


def _render_pitch_frame(
    segments: list[dict],
    frame_time_ms: float,
    panel_width: int,
    panel_height: int,
) -> np.ndarray:
    """
    Render one pitch guide frame as an RGBA numpy array.
    Shows a scrolling window of PITCH_WINDOW_MS centered on current position.
    Returns shape (panel_height, panel_width, 4) uint8.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    half_window = PITCH_WINDOW_MS / 2
    t_start = frame_time_ms - half_window
    t_end = frame_time_ms + half_window

    dpi = 100
    fig_w = panel_width / dpi
    fig_h = panel_height / dpi

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor((BG_COLOR[0]/255, BG_COLOR[1]/255, BG_COLOR[2]/255))
    ax.set_facecolor((BG_COLOR[0]/255, BG_COLOR[1]/255, BG_COLOR[2]/255))

    ax.set_xlim(t_start, t_end)
    ax.set_ylim(MIDI_LOW - 2, MIDI_HIGH + 2)
    ax.axis("off")

    # Draw pitch bars
    for seg in segments:
        s, e, midi = seg["start_ms"], seg["end_ms"], seg["midi_note"]
        if e < t_start or s > t_end:
            continue
        color = _midi_to_color(midi)
        rect = mpatches.FancyBboxPatch(
            (s, midi - 0.4), e - s, 0.8,
            boxstyle="round,pad=0.0",
            linewidth=0,
            facecolor=color,
            alpha=0.9,
        )
        ax.add_patch(rect)

    # Playhead line
    ax.axvline(x=frame_time_ms, color="#ffffff", linewidth=1.5, alpha=0.7)

    fig.tight_layout(pad=0)
    fig.canvas.draw()
    buf = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    buf = buf.reshape(panel_height, panel_width, 4)
    # ARGB → RGBA
    rgba = np.roll(buf, -1, axis=2)
    plt.close(fig)
    return rgba


def run(tmp_dir: str, title: str, artist: str) -> dict:
    """
    Compose final karaoke MP4.

    Args:
        tmp_dir: Directory with instrumental.wav, lyrics.lrc, pitch_segments.json
        title: Song title (for display)
        artist: Artist name (for display)

    Returns:
        dict with key 'output_path'
    """
    from moviepy.editor import (
        AudioFileClip, ColorClip, CompositeVideoClip,
        ImageSequenceClip, TextClip, VideoClip,
    )

    tmp_dir = Path(tmp_dir)
    instrumental_path = tmp_dir / "instrumental.wav"
    lrc_path = tmp_dir / "lyrics.lrc"
    pitch_segments_path = tmp_dir / "pitch_segments.json"
    output_path = tmp_dir / "output.mp4"

    for f in [instrumental_path, lrc_path, pitch_segments_path]:
        if not f.exists():
            raise FileNotFoundError(f"Required file missing: {f}")

    segments = json.loads(pitch_segments_path.read_text())
    lyrics = _parse_lrc(str(lrc_path))

    audio_clip = AudioFileClip(str(instrumental_path))
    duration = audio_clip.duration
    duration_ms = duration * 1000

    logger.info(f"Compositing video: duration={duration:.1f}s, fps={FPS}")

    # Background
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=BG_COLOR, duration=duration)

    # Title/artist header text
    header = TextClip(
        f"{title} — {artist}",
        fontsize=24,
        color="#888888",
        font="DejaVu-Sans",
    ).set_position(("center", 20)).set_duration(duration)

    # Lyric clips: show each line from its timestamp until the next
    lyric_clips = []
    for i, lyric in enumerate(lyrics):
        start_s = lyric["time_ms"] / 1000
        end_s = (lyrics[i + 1]["time_ms"] / 1000) if i + 1 < len(lyrics) else duration
        end_s = min(end_s, duration)
        clip_duration = max(0.1, end_s - start_s)

        txt = TextClip(
            lyric["text"],
            fontsize=FONT_SIZE,
            color=LYRIC_COLOR,
            font="DejaVu-Sans",
            method="caption",
            size=(VIDEO_WIDTH - 80, None),
            align="center",
        ).set_position(("center", VIDEO_HEIGHT - PITCH_PANEL_HEIGHT - 100)) \
         .set_start(start_s) \
         .set_duration(clip_duration)
        lyric_clips.append(txt)

    # Pitch guide panel — render frame by frame
    frames_dir = tmp_dir / "pitch_frames"
    frames_dir.mkdir(exist_ok=True)
    frame_count = int(duration * FPS)

    logger.info(f"Rendering {frame_count} pitch guide frames...")
    frame_paths = []
    for i in range(frame_count):
        frame_time_ms = (i / FPS) * 1000
        frame = _render_pitch_frame(
            segments, frame_time_ms,
            VIDEO_WIDTH, PITCH_PANEL_HEIGHT,
        )
        frame_path = frames_dir / f"frame_{i:06d}.png"
        from PIL import Image
        Image.fromarray(frame[:, :, :3], "RGB").save(str(frame_path))
        frame_paths.append(str(frame_path))

        if i % (FPS * 10) == 0:
            logger.info(f"  {i}/{frame_count} frames rendered")

    pitch_clip = ImageSequenceClip(frame_paths, fps=FPS) \
        .set_position(("left", VIDEO_HEIGHT - PITCH_PANEL_HEIGHT))

    # Composite everything
    all_clips = [bg, header] + lyric_clips + [pitch_clip]
    final = CompositeVideoClip(all_clips, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    final = final.set_audio(audio_clip)

    logger.info(f"Encoding MP4: {output_path}")
    final.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        ffmpeg_params=["-crf", "23"],
        logger=None,
    )

    logger.info(f"Video complete: {output_path}")
    return {"output_path": str(output_path)}
