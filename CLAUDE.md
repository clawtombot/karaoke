# CLAUDE.md

Guidance for Claude Code when working on PiKaraoke.

## Project Overview

PiKaraoke is a karaoke system for Raspberry Pi, Windows, macOS, and Linux. Web interface for YouTube song search, queuing, and playback with pitch shifting and streaming.

## Core Principles

**Single-owner maintainability:** Code clarity over documentation. Simplicity over flexibility. One source of truth.

## Refactoring

**Refactor iteratively as you work.** When touching code:

- Extract classes when a module has multiple responsibilities (like `Browser` was extracted from utilities)
- Extract functions when logic is repeated or a function exceeds ~50 lines
- Rename unclear variables/functions immediately
- Delete dead code - never comment it out
- Update related code consistently (no half-migrations)

**When to refactor:**

- Code you're modifying is hard to understand
- You're adding a third similar pattern (rule of three)
- A function/class is doing too many things

**When NOT to refactor:**

- Unrelated code "while you're in the area"
- Working code that you're not modifying
- To add flexibility you don't need yet

## Code Style

- PEP 8, 4 spaces, meaningful names
- Type hints required: modern syntax (`str | None`) — Python 3.10+ is the minimum, no `from __future__ import annotations` needed
- Concise docstrings for public APIs - explain "why", not "how"
- No emoji or unicode emoji substitutes

## Filename Conventions

YouTube video filenames use exactly 11-character IDs:

- PiKaraoke format: `Title---dQw4w9WgXcQ.mp4` (triple dash)
- yt-dlp format: `Title [dQw4w9WgXcQ].mp4` (brackets)

Only support these two patterns.

## Error Handling

- Catch specific exceptions, never bare `except:`
- Log errors, never swallow silently
- Use context managers for resources

## Testing

- pytest with mocked external I/O and subprocess operations only
- Test business logic and integration points
- Skip trivial getters/setters
- Use real `EventSystem` and `PreferenceManager` instances (they're lightweight)

## Deployment

The SvelteKit frontend is static — pikaraoke serves files from `frontend/dist/` on each request.

```bash
# Frontend-only changes: just rebuild, no restart needed
cd frontend && BASE_PATH=/karaoke npm run build
# Then hard-refresh the browser

# Backend (Python) changes: restart the pikaraoke process
# NanoClaw manages it — restart via launchctl or re-expose the app

# NanoClaw TypeScript changes: rebuild + restart NanoClaw
cd /path/to/nanoclaw && npm run build && launchctl kickstart -k gui/$(id -u)/com.nanoclaw
```

`BASE_PATH=/karaoke` is required for frontend builds — it sets the SvelteKit base path to match the NanoClaw proxy prefix. NanoClaw auto-injects this for builds via `expose_app`, but manual builds need it explicitly.

## Code Quality

```bash
# Run pre-commit checks
uv run pre-commit run --config code_quality/.pre-commit-config.yaml --all-files
```

Tools: Black (100 char), isort, pycln, pylint, mdformat.

Never commit to `master` directly.

## Pull Requests

PRs must include a test plan: a minimal checklist targeting only the changes made, enabling quick manual verification.

## WebSocket Event Checklist

When adding a new real-time feature synced between remote and TV:

1. **Remote page** (`routes/remote/+page.svelte`): `emit('event_name', value)` + `saveSongConfig()` if persistent
2. **Server relay** (`routes_fastapi/socket_events.py`): `@sio.on("event_name")` handler that calls `sio.emit("event_name", value, skip_sid=sid)`
3. **Splash/TV page** (`routes/splash/+page.svelte`): `on('event_name', handler)` in the socket listeners array
4. **Config save** (`saveSongConfig` in remote): include in the JSON body
5. **Config restore** (remote song change handler): read from `cfg` and `emit()` to sync TV

Missing ANY step = silent failure. Always grep for the existing pattern (e.g. `pitch_noise_gate`) and replicate all 5 steps.

## What NOT to Do

- Add unrequested features
- Add error handling for impossible states
- Create abstractions for single uses
- Write speculative "future-proofing" code
- Commit debug prints or commented code
