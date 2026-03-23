# HomeKaraoke Complete Redesign Plan

## Context

HomeKaraoke (PiKaraoke fork v1.19.0) is a self-hosted karaoke system with a Python/Flask backend, jQuery frontend, and WebSocket-based real-time communication. Full rewrite to professional-grade karaoke experience inspired by Apple Music Sing, YouTube Karaoke, Spotify, KaraFun, and SingStar.

Four interconnected goals:
1. **Backend modernization** — Flask + gevent → FastAPI + uvicorn (native async, no monkey-patching)
2. **Complete UX redesign** — Svelte 5 SPA with modern reactive UI
3. **Lyrics/subtitle system** — rich karaoke subtitles with word-level timing, romaji for CJK, fallback for missing lyrics
4. **Pitch visualization** — SingStar-style pitch graph from vocal stems + real-time mic input

---

## Part 1: Current State (Summary)

### Architecture
```
Frontend (jQuery + Jinja2 + Bulma + Socket.IO) → Flask Routes (16 blueprints) → Core Engine → FFmpeg + yt-dlp + demucs-mlx
```

### Feature Audit
| Feature | Status | Issue |
|---------|--------|-------|
| 6-stem mixer | Working | UI buried, tiny buttons |
| Pitch/key shift | Working | Hidden behind toggle |
| Fair queue | Working | Users don't know it exists |
| ASS subtitles | Partial | Only if .ass file exists alongside video |
| Lyrics display | **Missing** | No lyrics system |
| Word highlighting | **Missing** | No karaoke-style timing |
| CJK romanization | **Missing** | No romaji/pinyin |
| Pitch graph | **Missing** | No SingStar-style visualization |
| Favorites/history | **Missing** | Queue is ephemeral |

---

## Part 2: Frontend — Svelte 5 + Vite SPA

### Why Svelte 5 (not React/Vue/jQuery)

The deciding technical requirement is **60fps word-level lyric highlighting in a `requestAnimationFrame` loop**. This eliminates virtual DOM frameworks:

| Framework | rAF Hot Path | Bundle (gzip) | Mental Model |
|-----------|-------------|---------------|--------------|
| **Svelte 5** | Compiled → direct DOM update, no diffing | ~5KB | Simplest (runes, no dep arrays) |
| React 19 | `setState` → vDOM diff → patch DOM (60x/sec waste) | ~42KB | Hooks footguns (stale closures) |
| Vue 3 | Still vDOM internally, same overhead | ~33KB | Middle ground |
| Next.js | **Rejected** — SSR useless here, requires Node.js backend | N/A | Wrong tool |
| jQuery+Alpine | No component model, can't handle growing complexity | N/A | Doesn't solve problems |

**Key insight**: Every library we need is vanilla JS (socket.io-client, hls.js, SubtitlesOctopus, Web Audio API, Canvas API). The "React ecosystem advantage" doesn't apply — none of these have React-specific wrappers we'd miss.

Svelte 5 advantages for karaoke:
- `$state` rune → `wordIndex = newIndex` compiles to direct `element.className` update (no diffing)
- Built-in `transition:` and `animate:` directives for lyric entrance/exit
- `bind:value` for stem mixer sliders (no boilerplate)
- `use:action` for reusable DOM behaviors (`use:autoScroll` for lyrics)
- `{#each}` with keyed transitions for smooth queue reordering

### Backend Integration Architecture (FastAPI + uvicorn)
```
Development:
  Vite dev server (:5173) --proxy /api/*--> uvicorn (:5555)
  Socket.IO proxied through Vite to uvicorn

Production:
  npm run build → dist/ (static HTML/JS/CSS)
  FastAPI serves dist/index.html via catch-all route
  FastAPI serves dist/assets/* via StaticFiles mount
  FastAPI handles /api/* routes (routers, migrated from Flask blueprints)
  python-socketio AsyncServer handles WebSocket (ASGI mode)
```

### Frontend Module Structure
```
frontend/
  src/
    lib/
      stores/
        socket.svelte.ts      # Socket.IO connection + reactive state
        playback.svelte.ts    # Now-playing, position, queue
        lyrics.svelte.ts      # Current lyrics, active word/line
        stems.svelte.ts       # Stem mix state, Web Audio API
        pitch.svelte.ts       # Mic input, pitch detection
      audio/
        stem-mixer.ts         # Web Audio API AudioContext + 6 GainNodes
        pitch-detector.ts     # pitchy MPM algorithm + mic input
      lyrics/
        renderer.ts           # Word highlight timing, scroll logic
      player/
        hls-manager.ts        # HLS.js lifecycle
        video-sync.ts         # Position sync across devices
    routes/
      +layout.svelte          # Shell (nav, socket connection)
      splash/+page.svelte     # TV display (full-screen player)
      remote/+page.svelte     # Phone remote (controls + lyrics)
      search/+page.svelte     # Search + download
      queue/+page.svelte      # Queue management
    components/
      LyricsOverlay.svelte    # TV: word-by-word highlight overlay
      LyricsPanel.svelte      # Phone: scrollable synced lyrics
      PitchGraph.svelte       # Canvas pitch visualization
      StemMixer.svelte        # Compact stem controls
      NowPlaying.svelte       # Current song card
      QueueList.svelte        # Queue with drag-drop
  vite.config.ts
  tailwind.config.ts          # Extend Prisma tokens into Tailwind
```

### CSS Strategy: Tailwind v4 (structure) + Svelte scoped styles (effects)
- **Tailwind v4** for layout, spacing, grid, flex, responsive, glass containers (`backdrop-blur-*`)
- **Svelte scoped `<style>`** for karaoke-specific effects (word gradient sweep, `<ruby>` styling, canvas z-index)
- Prisma design tokens as CSS custom properties in Tailwind `@theme` block — themes swappable by changing tokens
- Dark mode only (karaoke is always dark)
- Themes/versions trivially swappable after build — change CSS custom properties, everything updates

---

## Part 3: Lyrics & Subtitle System

### Lyrics Library Evaluation (Research Findings)

| Library | NetEase YRC | LRCLIB | Musixmatch | CJK Roman. | Status |
|---------|-------------|--------|------------|-----------|--------|
| `syncedlyrics` | Line-level only (old API) | Yes | Yes | No | Stale (Jul 2024) |
| LDDC | Yes (desktop app) | No | No | No | Active (1.4K stars) |
| `karaoke-gen` | No | Yes | Yes | No | Very active (v0.147) |
| **Custom (our approach)** | **Yes (EAPI + YRC)** | **Yes** | **Fallback** | **Yes** | — |

**Decision**: Build a custom `pikaraoke/lib/lyrics/` module because:
- No single library combines NetEase YRC + LRCLIB + romanization
- LDDC is a Qt desktop app — extractable but messy
- `syncedlyrics` is stale and doesn't fetch YRC word-level data
- We need tight integration with our playback pipeline

### NetEase API Integration (Updated)

**The `tomm3hgunn/NetEaseMusicApi` repo is NOT usable** — it only hits the old `/api/` endpoint for line-level LRC. The real API:

```
POST https://interface.music.163.com/eapi/song/lyric/v1
Params: {"id": songId, "lv": "-1", "tv": "-1", "rv": "-1", "yv": "-1"}
Auth: Anonymous guest login via EAPI encryption (AES-CBC + RSA)
```

**Response fields:**
| Field | Content |
|-------|---------|
| `lrc` | Standard LRC — line-level (fallback) |
| `tlyric` | Translation LRC — line-level |
| `romalrc` | Romanization LRC — line-level (romaji/pinyin/romanized Korean) |
| `yrc` | **Word-level timing** (proprietary YRC format) |

**YRC format** (the key to word-level karaoke):
```
[lineStartMs,lineDurationMs](wordStartMs,wordDurationMs,0)word(nextStartMs,nextDurMs,0)word...
```
Example: `[20570,1900](20570,360,0)字(20930,150,0)符(21080,200,0)示(21280,190,0)例`

**Reference implementation**: Extract EAPI encryption + YRC parser from [LDDC](https://github.com/chenmozhijin/LDDC) (`LDDC/core/api/lyrics/ne.py`, `LDDC/core/parser/yrc.py`)

### Lyrics Pipeline
```
Song queued → LyricsManager.get_lyrics(title, artist)
  1. Check local cache (data/lyrics/{hash}.json)
  2. Check local .lrc/.ass alongside video
  3. NetEase: search → get song ID → fetch YRC + romalrc + tlyric
  4. LRCLIB: GET https://lrclib.net/api/get?artist=X&track_name=Y (line-level)
  5. YouTube subs: yt-dlp --write-subs (if downloaded from YT)
  → Parse all to unified LyricsLine[] format
  → If line-level only: estimate word timing (proportional distribution)
  → If CJK without romalrc: pykakasi (JP) / pypinyin (CN) / korean-romanizer (KR)
  → Cache to data/lyrics/{hash}.json
  → Serve via /api/lyrics/{stream_uid}
```

### Word-Level Timing Estimation (when YRC unavailable)
```python
def estimate_word_timing(line_start_ms, line_end_ms, text):
    # CJK: each character ≈ one syllable, equal distribution
    # Latin: split on spaces, distribute proportionally by char count
    duration = line_end_ms - line_start_ms
    if is_cjk(text):
        chars = list(text.replace(" ", ""))
        per_char = duration / len(chars)
        return [LyricsWord(start=line_start_ms + i*per_char,
                          end=line_start_ms + (i+1)*per_char,
                          text=c) for i, c in enumerate(chars)]
    else:
        words = text.split()
        total_chars = sum(len(w) for w in words)
        offset = line_start_ms
        result = []
        for w in words:
            word_dur = duration * (len(w) / total_chars)
            result.append(LyricsWord(start=offset, end=offset+word_dur, text=w))
            offset += word_dur
        return result
```

### Backend Modules
```
pikaraoke/lib/lyrics/
    __init__.py
    manager.py          # LyricsManager — orchestrates sources, caching
    models.py           # LyricsLine, LyricsWord, SongLyrics dataclasses
    netease.py          # EAPI encryption + search + YRC fetch
    yrc_parser.py       # Parse YRC format to LyricsWord[]
    lrclib.py           # LRCLIB REST API client
    lrc_parser.py       # Parse standard/enhanced LRC
    word_estimator.py   # Proportional word timing from line timing
    romanizer.py        # CJK romanization (pykakasi, pypinyin)
    cache.py            # JSON file cache in data/lyrics/

pikaraoke/lib/pitch/
    __init__.py
    extractor.py        # Offline: vocal stem → pitch_data.json (CREPE/pYIN)
    models.py           # PitchNote dataclass

pikaraoke/routes/lyrics.py   # /api/lyrics/<stream_uid>, /api/lyrics/search, /api/lyrics/offset
pikaraoke/routes/pitch.py    # /api/pitch/<stream_uid> — serve precomputed pitch JSON
```

---

## Part 4: Pitch Graph Visualization (NEW)

### Overview
SingStar-style scrolling pitch graph showing reference melody + singer's real-time pitch. Positioned at top of splash screen in a transparent glass container.

### Offline Pipeline (per song, alongside stem splitting)
```
demucs separate song → vocals.wav
  ↓
torchcrepe.predict(vocals.wav, viterbi=True)  # Apple Silicon MPS-accelerated
  ↓
pitch_data.json: [{t: 0.05, hz: 440.0, midi: 69}, ...]
  ↓
Serve via /api/pitch/{stream_uid}
```

**Libraries (Python, offline):**
- `torchcrepe` — PyTorch CREPE, best on Apple Silicon MPS (already have PyTorch for demucs)
- Fallback: `librosa.pyin` — no GPU needed, good accuracy
- Integration: Run in the stem splitter worker alongside demucs

### Real-Time Mic Pitch Detection (Browser)
```javascript
// pitchy (npm) — McLeod Pitch Method, ESM, ~5KB
import { PitchDetector } from 'pitchy';

const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    deviceId: { exact: selectedDeviceId },  // Yamaha MG10XU or phone mic
    echoCancellation: false,   // CRITICAL: disable for vocal input
    noiseSuppression: false,
    autoGainControl: false
  }
});

const ctx = new AudioContext();
const source = ctx.createMediaStreamSource(stream);
const analyser = ctx.createAnalyser();
analyser.fftSize = 2048;
source.connect(analyser);

const detector = PitchDetector.forFloat32Array(analyser.fftSize);
const input = new Float32Array(detector.inputLength);

function detect() {
  analyser.getFloatTimeDomainData(input);
  const [pitch, clarity] = detector.findPitch(input, ctx.sampleRate);
  if (clarity > 0.95 && pitch > 60) {
    // pitch in Hz → render on Canvas
  }
  requestAnimationFrame(detect);
}
```

**Audio input devices:**
- **Yamaha MG10XU**: USB audio interface → enumerates in `mediaDevices.enumerateDevices()` as standard input. Works perfectly.
- **Phone mic**: Default `getUserMedia()`. Works.
- **JBL PartyBox**: Bluetooth output only — browser can't capture from it. Would need system loopback (BlackHole on macOS). Not recommended.

### Canvas Rendering (HTML5 Canvas 2D — WebGL overkill)
```
┌──────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════╗    │
│  ║  PITCH GRAPH (glass container)       ║    │
│  ║                                      ║    │
│  ║  ▬▬▬▬▬   ▬▬▬▬   ▬▬▬▬▬▬▬   ← ref bars║   │
│  ║           ●                 ← singer ║    │
│  ║     ▬▬▬▬▬▬▬    ▬▬▬▬▬▬              ║    │
│  ║                                      ║    │
│  ╚═══════════════════════════════════════╝    │
│                                              │
│          VIDEO PLAYER (dimmed)               │
│                                              │
│  ┌───────────────────────────────────────┐   │
│  │  LYRICS (word highlight overlay)      │   │
│  │  駆け出した   先に   見える            │   │
│  │  Kakedashita  saki ni  mieru          │   │
│  └───────────────────────────────────────┘   │
│                                              │
│  🎤 Tom • 夜に駆ける • ▶━━━━━░░░ 2:14/4:18 │
│  UP NEXT: Bohemian Rhapsody • Sarah          │
└──────────────────────────────────────────────┘
```

**Color coding (SingStar standard):**
- Green (`#00ff88`): within 50 cents (0.5 semitone) — on pitch
- Yellow (`#ffdd00`): 50–150 cents — close
- Red (`#ff4444`): >150 cents — off pitch

**Glass container styling:**
```css
.pitch-container {
  backdrop-filter: blur(12px);
  background: rgba(13, 6, 24, 0.4);
  border: 1px solid rgba(124, 58, 237, 0.2);
  border-radius: 12px;
}
```

---

## Part 5: Word Highlighting (ON the word itself)

Word highlighting is a **CSS gradient sweep ON each word**, not a bar above. The active word gets a left-to-right color fill that sweeps across it during its timing window.

### Implementation
```css
/* Each word is a <span> with data attributes for timing */
.lyric-word {
  color: rgba(240, 236, 255, 0.35);  /* dim future words */
  transition: none;
  display: inline-block;
}

.lyric-word.sung {
  color: #f0ecff;  /* bright — already sung */
}

/* Active word: gradient sweep left→right */
.lyric-word.active {
  background: linear-gradient(
    90deg,
    var(--pr-teal) 0%,       /* sung portion */
    var(--pr-teal) var(--progress),
    rgba(240, 236, 255, 0.35) var(--progress),
    rgba(240, 236, 255, 0.35) 100%
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-shadow: 0 0 20px rgba(0, 210, 255, 0.4);  /* glow */
}
```

**JS drives `--progress` via rAF:**
```javascript
function updateLyrics(currentMs) {
  const word = getCurrentWord(currentMs);
  if (word) {
    const progress = (currentMs - word.start) / (word.end - word.start);
    activeEl.style.setProperty('--progress', `${progress * 100}%`);
  }
  requestAnimationFrame(() => updateLyrics(audio.currentTime * 1000));
}
```

### CJK Romanization Display (HTML `<ruby>`)
```html
<!-- Native browser support, universal 2023+ -->
<ruby class="lyric-word active" style="--progress: 45%">
  駆け出した
  <rt>かけだした</rt>   <!-- or romaji: Kakedashita -->
</ruby>
```

Romanization appears **above** the word in smaller text via native `<ruby>/<rt>` — no absolute positioning hacks needed.

---

## Part 6: Stem Mixer — Compact Symbolic Design (Mobile)

### Problem with Current Design
6 labeled buttons (`Drums`, `Bass`, `Other`, `Vocals`, `Guitar`, `Piano`) in a grid takes too much space. On phone, this crowds out lyrics and pitch graph.

### New Design: Icon-Only Toggle Row + Presets

```
┌─ MIXER ──────────────────────────────┐
│                                      │
│  [🎤 Karaoke]  [🎵 Original]  [🎧 Practice] │  ← Quick presets
│                                      │
│  🥁  🎸  🎹  🎤  🎸  🔊              │  ← Icon toggles (tap to mute)
│  ●   ●   ●   ○   ●   ●              │  ← Active dots below
│                                      │
└──────────────────────────────────────┘
```

**Presets:**
- **Karaoke** (🎤): Vocals OFF, everything else ON — the default karaoke mode
- **Original** (🎵): All stems ON — hear the original song
- **Practice** (🎧): Vocals at 30% volume — hear a faint guide

**Icon toggles**: Single row of 6 icons. Tapped icon toggles dim/bright. Active = bright teal dot below. Inactive = dim. Long-press shows stem name tooltip.

**Svelte component:**
```svelte
<div class="flex gap-3 justify-center">
  {#each stems as stem}
    <button
      on:click={() => toggleStem(stem.name)}
      class="stem-icon"
      class:active={stem.enabled}
      title={stem.label}>
      <i class="ti ti-{stem.icon}"></i>
      <span class="stem-dot" class:on={stem.enabled}></span>
    </button>
  {/each}
</div>
```

Takes ~40px height vs ~120px for the current grid. Leaves room for lyrics panel + pitch graph on phone.

---

## Part 7: Backend — Flask to FastAPI Migration

### Why FastAPI (not keep Flask, not Quart)

**The core problem**: Flask + gevent `monkey.patch_all()` (app.py:3) is actively harmful:
- **PyTorch MPS conflict**: gevent can't patch C-level GPU dispatch — demucs/CREPE block the event loop
- **Subprocess fragility**: FFmpeg via subprocess holds OS threads gevent can't cooperativize
- **No native async**: NetEase + LRCLIB API calls block greenlets

| Dimension | Flask (current) | FastAPI (target) |
|-----------|----------------|-----------------|
| Async | gevent monkey-patch | Native async/await |
| WebSocket | Flask-SocketIO (gevent) | python-socketio AsyncServer (ASGI) |
| API docs | Flask-smorest (bolted on) | Built-in OpenAPI (automatic) |
| Validation | Manual | Pydantic v2 (automatic) |
| PyTorch | Conflicts with gevent | run_in_executor — clean thread pool |
| Subprocess | Blocked by greenlets | asyncio.create_subprocess_exec |
| HTTP client | requests (blocking) | httpx.AsyncClient (non-blocking) |
| SQLite | Blocking | aiosqlite |
| Ecosystem | Mature but declining | 80K stars, Netflix/Uber/MS |

**Why not Quart**: Only 3K stars vs 80K. Flask extension compat incomplete. Smaller community for troubleshooting.

### Architecture
```
uvicorn (ASGI server, :5555)
  |-- socketio.ASGIApp (outer ASGI wrapper)
        |-- socketio.AsyncServer (rooms, namespaces, events)
        |     |-- namespace / (playback sync, stem mixer, notifications)
        |     |-- events: play, pause, skip, stem_toggle, playback_position
        |-- FastAPI app (inner HTTP routes)
              |-- /api/queue, /api/search, /api/stream, /api/stems
              |-- /api/lyrics, /api/pitch, /api/now, /api/prefs
              |-- /api/files, /api/admin
              |-- /* catch-all (serve Svelte SPA dist/)

asyncio event loop
  |-- ThreadPoolExecutor -> demucs, torchcrepe (PyTorch MPS)
  |-- asyncio.create_subprocess_exec -> FFmpeg, yt-dlp
  |-- httpx.AsyncClient -> NetEase API, LRCLIB
  |-- aiosqlite -> SQLite
```

### Socket.IO Migration (same python-socketio library)
```python
# Flask-SocketIO (current)                   # python-socketio ASGI (target)
from flask_socketio import SocketIO           import socketio
sio = SocketIO(app, async_mode="gevent")      sio = socketio.AsyncServer(async_mode="asgi")
                                              combined = socketio.ASGIApp(sio, fastapi_app)

@socketio.on("stem_toggle")                  @sio.on("stem_toggle")
def handle(stem):                             async def handle(sid, stem):
    emit("stem_mix_update", mix)                  await sio.emit("stem_mix_update", mix)
```

### Key Files to Transform
| Flask File | FastAPI File | Change |
|-----------|-------------|--------|
| app.py (Flask + gevent) | app.py (FastAPI + uvicorn) | Full rewrite |
| routes/*.py (16 blueprints) | routes/*.py (16 APIRouters) | Route decorators + async |
| lib/current_app.py | lib/dependencies.py | Flask g -> FastAPI Depends() |
| karaoke.py (Karaoke class) | karaoke.py (unchanged core) | Remove Flask coupling |
| lib/stream_manager.py | lib/stream_manager.py | subprocess -> asyncio subprocess |

---

## Part 8: Dependency Updates

### Python Dependencies (FastAPI stack)
```toml
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.34",
  "python-socketio>=5.12",
  "httpx>=0.28",
  "aiosqlite>=0.20",
  "python-multipart>=0.0.18",
  "qrcode[png]==8.2",
  "psutil==7.2.1",
  "Babel==2.17.0",
  "ffmpeg-python==0.2.0",
  "yt-dlp[default]>=2026.03",
  "torchcrepe>=0.0.22",
  "pykakasi>=2.3.0",
  "pypinyin>=0.53.0",
  "pycryptodomex>=3.21.0",
]
# REMOVED: Flask, Flask-SocketIO, Flask-Babel, Flask-smorest,
#          gevent, geventwebsocket, flask-paginate
```

### Frontend Dependencies (Svelte SPA)
```json
{
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^5.0",
    "svelte": "^5.54",
    "vite": "^8.0",
    "tailwindcss": "^4.0",
    "@tailwindcss/vite": "^4.0",
    "typescript": "^5.7"
  },
  "dependencies": {
    "socket.io-client": "^4.8.3",
    "hls.js": "^1.6.15",
    "pitchy": "^4.2",
    "js-cookie": "^3.0.5"
  }
}
```

---

## Part 9: Implementation — Single Phase 0

Everything ships as one integrated phase. No half-migrations. Build the complete new stack, verify end-to-end, then swap.

### Phase 0: Complete Rebuild

**0a. FastAPI Backend Scaffold**
- New app.py: FastAPI + uvicorn + python-socketio AsyncServer
- Migrate karaoke.py: remove Flask app context coupling, use FastAPI Depends()
- Migrate 16 Flask blueprints to 16 FastAPI APIRouters (async, Pydantic models)
- Migrate Socket.IO events: @socketio.on() to @sio.on() (async)
- Replace requests with httpx.AsyncClient
- Replace subprocess blocking with asyncio.create_subprocess_exec for FFmpeg/yt-dlp
- Replace SQLite with aiosqlite
- **Verify**: uvicorn starts, /api/now returns JSON, Socket.IO connects

**0b. Lyrics Backend**
- Build pikaraoke/lib/lyrics/ module (NetEase EAPI + LRCLIB + YRC parser + romanizer + cache)
- Build pikaraoke/routes/lyrics.py API router
- Extend PlaybackController with lyrics URL in now-playing state
- **Verify**: /api/lyrics/{stream_uid} returns word-timed JSON with romanization

**0c. Pitch Extraction Pipeline**
- Add torchcrepe to stem splitter worker (runs after demucs via run_in_executor)
- Build pikaraoke/lib/pitch/extractor.py (vocal.wav to pitch_data.json)
- Build pikaraoke/routes/pitch.py API router
- **Verify**: /api/pitch/{stream_uid} returns precomputed pitch contour

**0d. Svelte Frontend Scaffold**
- Create frontend/ directory with Vite + Svelte 5 + Tailwind
- Extract Prisma CSS tokens into Tailwind config
- Build socket store, playback store, lyrics store
- Set up Vite proxy to uvicorn dev server
- **Verify**: SPA loads, connects to Socket.IO, displays now-playing from API

**0e. Splash Screen (TV Display)**
- Build Svelte splash route with video player, HLS.js, SubtitlesOctopus
- Build LyricsOverlay.svelte (word-by-word highlight with CSS gradient sweep)
- Build PitchGraph.svelte (Canvas 2D scrolling reference + singer dot)
- Build stem mixer (Web Audio API AudioContext + 6 GainNode)
- Socket.IO integration for master/slave sync
- **Verify**: Full TV karaoke experience with video + lyrics + pitch graph + stems

**0f. Mobile Remote (Phone)**
- Build Svelte remote route with bottom tab nav
- Build LyricsPanel.svelte (scrollable synced lyrics with romaji)
- Build compact stem mixer with icon toggles + presets
- Playback controls, volume, key change
- Queue preview + Add Song shortcut
- **Verify**: Phone controls playback, lyrics scroll in sync

**0g. Search, Queue and Polish**
- Build search page (unified local + YouTube, card layout)
- Build queue page (drag-drop reorder, favorites)
- Song history (SQLite via aiosqlite)
- Audio input device selector (for pitch graph mic source)
- Lyrics timing offset adjustment (plus/minus 100ms buttons)
- **Verify**: Complete app, all features working end-to-end

---

## Part 9: Verification

### Automated Tests
- **Python**: pytest for lyrics parsers (YRC, LRC, ASS), word estimator, romanizer, NetEase client (mocked), pitch extractor
- **Frontend**: Svelte component tests with Vitest + @testing-library/svelte for lyrics renderer, pitch graph

### Manual Testing Checklist
- [ ] English song: lyrics highlight word-by-word on TV
- [ ] Japanese song: romaji shown above kanji via `<ruby>`, highlights sync
- [ ] Chinese song: pinyin above hanzi
- [ ] Korean song: romanization above hangul
- [ ] Missing lyrics: graceful "No lyrics available" state
- [ ] Pitch graph: reference bars scroll, singer dot tracks mic input
- [ ] Yamaha MG10XU: selectable as audio input, pitch detection works
- [ ] Stem mixer presets: Karaoke/Original/Practice switch correctly
- [ ] Individual stem toggles work, compact icons clear
- [ ] Phone remote: lyrics scroll in sync, controls responsive
- [ ] Multiple splash screens: master/slave position sync
- [ ] Socket.IO reconnect: recovers gracefully
- [ ] Queue: drag-drop reorder, add from search, favorites persist

### Build & Deploy
```bash
cd frontend && npm run build                    # Svelte -> dist/
cd .. && uv run pytest                           # Python tests
uv run pre-commit run --all-files                # Code quality
uvicorn pikaraoke.app:combined --port 5555       # Manual test at http://localhost:5555
```

---

## Key Reference Projects

| Project | Use For |
|---------|---------|
| [LDDC](https://github.com/chenmozhijin/LDDC) | Extract NetEase EAPI encryption + YRC parser code |
| [AllKaraoke](https://github.com/Asvarox/allkaraoke) | Reference: TypeScript web karaoke with pitch detection + scoring |
| [UltraSinger](https://github.com/rakuri255/UltraSinger) | Reference: demucs + CREPE → UltraStar pitch file pipeline |
| [pitchy](https://github.com/ianprime0509/pitchy) | Browser McLeod Pitch Method (npm package) |
| [torchcrepe](https://github.com/maxrmorrison/torchcrepe) | PyTorch CREPE pitch extraction (Apple Silicon MPS) |
| [lrclib.net](https://lrclib.net/docs) | Free synced lyrics API (~3M tracks, no auth) |
