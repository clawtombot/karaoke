# HomeKaraoke — Project Plan

## Goal

Best-of-both-worlds self-hosted karaoke system combining the actively maintained `vicwomg/pikaraoke` base with DNN vocal splitting, a modern Svelte SPA frontend, and enhanced features (lyrics, pitch graph, stem mixer).

## Lineage

| Repo | Role |
|------|------|
| [`vicwomg/pikaraoke`](https://github.com/vicwomg/pikaraoke) | Upstream base — YouTube download, queue, WebSocket playback, multi-language, modular Python |
| [`xuancong84/pikaraoke`](https://github.com/xuancong84/pikaraoke) | Feature reference (OpenHomeKaraoke) — DNN vocal splitting, stream-to-HTTP |
| [`tsurumeso/vocal-remover`](https://github.com/tsurumeso/vocal-remover) | Original vocal model (replaced by demucs-mlx) |
| `tomm3hgunn/HomeKaraoke` (private) | This repo — the merged result |

## Stack

- **Backend:** Python 3.10+, FastAPI + uvicorn (migrated from Flask), Socket.IO
- **Frontend:** SvelteKit 2 + Svelte 5, Tailwind CSS v4, Vite, HLS.js
- **Audio:** yt-dlp, ffmpeg, demucs-mlx (6-stem separation on Apple Silicon)
- **Extras:** Word-level lyrics (multi-source), pitch extraction pipeline, CJK romanization

## What was kept from vicwomg

- YouTube download + queue (yt-dlp)
- Phone web interface via QR code
- WebSocket player communication
- Splash screen background video
- Multi-language support (20+ languages)
- Modular codebase

## What was added beyond OpenHomeKaraoke

- Modern SPA frontend (Svelte 5 + Tailwind) replacing Flask templates
- 6-stem mixer (vocals, drums, bass, guitar, piano, other) via demucs-mlx
- Word-level synchronized lyrics with karaoke highlighting
- Pitch extraction pipeline for SingStar-style graph
- CJK romanization (furigana/pinyin)
- FastAPI backend (async, better WebSocket support)
- Browse page with alphabet filter, pagination, rename with Last.fm suggestions
- Settings page with toggle preferences and admin actions

## Feature Status

| Feature | Status |
|---------|--------|
| YouTube search + thumbnails | Done |
| YouTube download | Done |
| Video preview modal | Done |
| Local autocomplete | Done |
| Queue from search | Done |
| Playback controls (pause, skip, restart, volume) | Done |
| Key transpose | Done |
| 6-stem mixer | Done |
| Now playing + progress | Done |
| Queue management (drag-drop reorder) | Done |
| Lyrics + word highlight | Done |
| Pitch graph (SingStar-style) | Done |
| CJK romanization | Done (backend) |
| Browse library (alphabet filter, pagination) | Done |
| Song edit/rename (Last.fm suggestions) | Done |
| Settings (preferences, admin actions) | Done |
| TV splash screen (HLS video, lyrics overlay, pitch) | Done |
| File browser (full admin page) | Deferred |
| Admin auth (password gate) | API ready, no UI |

## Design

Design system: **Prisma** — dark glassmorphism with purple/teal gradients.

Storyboard screenshots in `storyboard/` directory, numbered sequentially.

Fonts: Syne (display), Inter (body), JetBrains Mono (mono).

## Standards

- Always check `vicwomg/pikaraoke` latest before implementing — may already have the feature
- PyTorch/demucs GPU optional — CPU fallback must always work
- Test: song plays, instrumental mode works, queue persists
- Research saved to `research/` with date stamps
