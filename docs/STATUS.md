# TommysKaraoke — Implementation Status

Last updated: 2026-03-23

## Architecture (Complete)

| Component                       | Status | Notes                                              |
| ------------------------------- | ------ | -------------------------------------------------- |
| FastAPI + uvicorn backend       | Done   | Migrated from Flask, async Socket.IO               |
| SvelteKit 2 + Svelte 5 frontend | Done   | Static adapter, BASE_PATH=/karaoke                 |
| Socket.IO real-time             | Done   | WebSocket through NanoClaw proxy                   |
| HLS streaming (fMP4)            | Done   | FFmpeg transcoding, hls.js on splash               |
| 6-stem separation               | Done   | Explicit backend/model config, no baked-in weights |
| NanoClaw reverse proxy          | Done   | HTTP + WebSocket + query string fix                |
| Design system ("Prisma")        | Done   | Dark glassmorphism, purple/teal gradients          |

## Pages (Complete)

| Page             | Route       | Status | Notes                                        |
| ---------------- | ----------- | ------ | -------------------------------------------- |
| Landing          | `/`         | Done   | Now playing card, quick links                |
| Remote (phone)   | `/remote`   | Done   | Controls, stem mixer, lyrics panel, tab bar  |
| Search           | `/search`   | Done   | YouTube search + download, enqueue           |
| Queue            | `/queue`    | Done   | Drag reorder, now-playing card, progress bar |
| Browse (library) | `/browse`   | Done   | A-Z strip, pagination, edit/rename, delete   |
| Settings         | `/settings` | Done   | Preferences, system info, admin actions      |
| Splash (TV)      | `/splash`   | Done   | Full-screen video, now-playing bar, up-next  |

## Features — Confirmed Working (tested through proxy)

| Feature                     | Evidence                                           |
| --------------------------- | -------------------------------------------------- |
| Video playback (HLS)        | Splash plays video with progress bar               |
| Song queueing               | Enqueue via search/browse, auto-play               |
| Pause / Resume              | Toggles play/pause icon, splash responds           |
| Skip                        | Clears playback, returns to idle                   |
| Restart                     | Restarts song from beginning                       |
| Volume control              | Slider on remote, propagates to splash             |
| Key transpose               | +/- semitones with apply button                    |
| Stem toggle (individual)    | 6 stems on/off, UI updates reactively              |
| Stem presets                | Karaoke (vocals off), Original, Practice           |
| Live stem sync to splash    | $effect reactivity fix — mix changes propagate     |
| WebSocket through proxy     | Query string preserved (EIO=4&transport=websocket) |
| Tabler + Font Awesome icons | All icons render (drum, guitar, mic, piano, etc.)  |
| Background video (idle)     | Plays on splash when no song queued                |
| Auto-play next in queue     | Run loop pops queue automatically                  |
| Song download (yt-dlp)      | Downloads from YouTube via search page             |

## Features — Still To Verify / Complete

| Feature                      | Status              | Notes                                      |
| ---------------------------- | ------------------- | ------------------------------------------ |
| Lyrics overlay (splash)      | Built, untested     | Needs .ass subtitle file or lyrics API     |
| Word-level highlighting      | Built, untested     | Requires timed lyrics data                 |
| Pitch graph (SingStar-style) | Built, untested     | Needs pitch data from vocal stem           |
| Pitch detection (mic input)  | Built, untested     | Web Audio API pitch detector on splash     |
| Score screen                 | Not started         | Post-song scoring based on pitch accuracy  |
| Favorites / history          | Not started         | Planned in design doc                      |
| CJK romanization             | Not started         | Romaji/pinyin for lyrics                   |
| Browse: edit/rename songs    | Built, untested     | Last.fm name suggestions, modal UI         |
| Browse: delete songs         | Built, untested     | Confirm dialog, API wired                  |
| Settings: all preferences    | Built, untested     | 12 boolean + 6 numeric prefs               |
| Settings: admin actions      | Built, untested     | Refresh songs, update yt-dlp, quit/reboot  |
| In-app download reliability  | Needs investigation | Downloads sometimes fail silently via UI   |
| Stem progress indicator      | Built, untested     | Shows "Splitting... X/6" during processing |
| Multi-splash sync            | Built, untested     | Master/slave election, position sync       |

## Known Issues

| Issue                       | Severity | Notes                                                                     |
| --------------------------- | -------- | ------------------------------------------------------------------------- |
| Songs in wrong download dir | Low      | `songs/` dir in project vs `~/tommyskaraoke-songs/` — configure download_path |
| App manager stale PID       | Low      | Manual process kill leaves DB status stale                                |
| Browser cache after deploys | Low      | Users need Cmd+Shift+R after frontend rebuilds                            |
| `-vsync` ffmpeg deprecation | Info     | Warning in logs, still works (use `-fps_mode` in future)                  |

## Commits This Session

- `d2c3b39` fix: add Tabler Icons CDN and fix live stem toggle on splash
- `6abbf26` test: icon rendering, stem toggle, pause/play screenshots
- `a83d880` fix: use valid Tabler icon for 'other' stem (ti-wave-square)
- `329df54` fix: stem icons now represent their actual instruments
- `3ff6164` fix: use real instrument icons for stem mixer (Font Awesome + Tabler)
