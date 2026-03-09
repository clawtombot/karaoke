#!/usr/bin/env python3
"""
PHANTOM Karaoke Pipeline — Main Entry Point
Song in, karaoke MP4 out.

Usage:
    python pipeline.py --input song.mp3 --output output.mp4 --title "Song Name" --artist "Artist"

Stages (sequential):
    1. stem_separation  — BS-Roformer via audio-separator
    2. lyrics           — LRCLib.net → WhisperX fallback
    3. pitch            — torchcrepe F0 → MIDI segments JSON
    4. video            — matplotlib + MoviePy + FFmpeg → MP4

Intermediate files written to ./tmp/{sanitized_title}/
"""

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

from stages import stem_separation, lyrics, pitch, video


def sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]


def run_pipeline(
    input_path: str,
    output_path: str,
    title: str,
    artist: str,
    tmp_base: str = "./tmp",
) -> str:
    """
    Run full karaoke pipeline.

    Args:
        input_path: Path to input audio file
        output_path: Path for final MP4 output
        title: Song title
        artist: Artist name
        tmp_base: Base directory for intermediate files

    Returns:
        Path to output MP4
    """
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    tmp_dir = Path(tmp_base) / sanitize(title)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== PHANTOM Karaoke Pipeline ===")
    logger.info(f"Input:  {input_path}")
    logger.info(f"Output: {output_path}")
    logger.info(f"Title:  {title}")
    logger.info(f"Artist: {artist}")
    logger.info(f"Tmp:    {tmp_dir}")
    logger.info("")

    t_total = time.time()

    # Stage 1: Stem separation
    logger.info("[ Stage 1/4 ] Stem separation")
    t0 = time.time()
    stem_result = stem_separation.run(str(input_path), str(tmp_dir))
    logger.info(f"  Done in {time.time() - t0:.1f}s — {stem_result}")

    # Stage 2: Lyrics
    logger.info("[ Stage 2/4 ] Lyrics")
    t0 = time.time()
    lyrics_result = lyrics.run(str(tmp_dir), title, artist)
    logger.info(f"  Done in {time.time() - t0:.1f}s — source={lyrics_result['source']}")

    # Stage 3: Pitch extraction
    logger.info("[ Stage 3/4 ] Pitch extraction")
    t0 = time.time()
    pitch_result = pitch.run(str(tmp_dir))
    logger.info(f"  Done in {time.time() - t0:.1f}s — {pitch_result}")

    # Stage 4: Video composition
    logger.info("[ Stage 4/4 ] Video composition")
    t0 = time.time()
    video_result = video.run(str(tmp_dir), title, artist)
    logger.info(f"  Done in {time.time() - t0:.1f}s")

    # Move output to requested path
    import shutil
    shutil.move(video_result["output_path"], str(output_path))

    elapsed = time.time() - t_total
    logger.info(f"\n=== Pipeline complete in {elapsed:.1f}s ===")
    logger.info(f"Output: {output_path}")

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="PHANTOM Karaoke Pipeline — song in, MP4 out"
    )
    parser.add_argument("--input", required=True, help="Input audio file (mp3, wav, flac)")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--title", required=True, help="Song title")
    parser.add_argument("--artist", required=True, help="Artist name")
    parser.add_argument("--tmp", default="./tmp", help="Temp directory (default: ./tmp)")
    args = parser.parse_args()

    try:
        run_pipeline(
            input_path=args.input,
            output_path=args.output,
            title=args.title,
            artist=args.artist,
            tmp_base=args.tmp,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
