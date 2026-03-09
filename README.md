# Karaoke — PHANTOM

Upload any song → get a karaoke MP4 with clean instrumental + timed lyrics + pitch guide.

**Live app:** https://karaoke-phantom.pages.dev

---

## Architecture

- **Frontend** (static) — deployed to Cloudflare Pages, this repo
- **Backend** (local) — FastAPI server, runs on your machine, processes audio

The frontend is a static HTML page. It connects to a backend server you run locally or on your host. The backend URL is configurable in the app's settings panel.

---

## Running the Backend (required for processing)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy config (no keys needed — fully local)
cp config.env .env

# Start server on port 8001
python server.py
```

Then open the app, go to Settings, and set the Backend URL to `http://localhost:8001` (or your server's address).

### First run

The first song you process will download the stem separation model (~500MB). Subsequent runs are instant.

### Persistent server (macOS launchd)

```bash
cp com.phantom.karaoke.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.phantom.karaoke.plist
```

---

## Stack

| Component | Tool |
|-----------|------|
| Stem separation | `audio-separator` + BS-Roformer |
| Lyrics | LRCLib.net API → WhisperX fallback |
| Pitch extraction | `torchcrepe` (Viterbi) |
| Video render | `matplotlib` + `MoviePy` + FFmpeg |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla HTML/CSS/JS |

---

## CLI Usage

```bash
python pipeline.py \
  --input song.mp3 \
  --output output.mp4 \
  --title "Song Name" \
  --artist "Artist Name"
```

---

## ⚠ Copyright

For personal/demo use only. Never upload or distribute outputs. YouTube Content ID detects karaoke outputs.

---

## Development

Frontend is a single `index.html`. Edit and push to `main` → auto-deploys via GitHub Actions.
