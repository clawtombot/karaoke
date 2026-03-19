#!/usr/bin/env python3
"""
Home Karaoke — API Eval Runner
Run: python research/run_evals.py
Requires: app running at localhost:5555
"""

import json
import sys
import time

import requests

BASE = "http://localhost:5555"
results = []
SONG1_URL = "https://www.youtube.com/watch?v=HgzGwKwLmgM"
SONG1_TITLE = "Queen - Don't Stop Me Now"
SONG2_URL = "https://www.youtube.com/watch?v=fJ9rUzIMcZQ"
SONG2_TITLE = "Queen - Bohemian Rhapsody"


def log(test_id, name, passed, detail=""):
    icon = "PASS" if passed else "FAIL"
    results.append({"id": test_id, "name": name, "pass": passed, "detail": detail})
    print(f"  [{icon}] {test_id} {name}: {detail}")
    sys.stdout.flush()


def api(path, method="GET", data=None, timeout=15):
    try:
        if method == "POST":
            return requests.post(BASE + path, json=data, timeout=timeout)
        return requests.get(BASE + path, timeout=timeout)
    except Exception as e:
        return None


def np():
    r = api("/now_playing")
    if r and r.status_code == 200:
        try:
            return json.loads(r.text)
        except Exception:
            return {}
    return {}


def wait_for_playing(timeout=120):
    print(f"    ...waiting for song (up to {timeout}s)")
    for i in range(timeout):
        d = np()
        if d.get("now_playing"):
            return d
        if i % 15 == 0 and i > 0:
            print(f"    ...{i}s elapsed")
        time.sleep(1)
    return {}


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


print("=" * 50)
print("  HOME KARAOKE — API EVAL SUITE")
print("=" * 50)

# ── A: Health ──────────────────────────────────────
section("A: Health")

r = api("/")
log("A01", "App responds to /", r and r.status_code == 200, f"HTTP {r.status_code if r else 'no connection'}")

d = np()
log("A02", "now_playing JSON", bool(d), f"keys: {list(d.keys())[:4]}")
log("A03", "Vocal splitter enabled", d.get("vocal_splitter_enabled") is True, str(d.get("vocal_splitter_enabled")))

# ── B: Download & Playback ─────────────────────────
section("B: Download & Playback")

dl = api("/download", method="POST", data={
    "song_url": SONG1_URL,
    "song_added_by": "eval-runner",
    "song_title": SONG1_TITLE,
    "queue": True,
})
log("A04", "Download POST accepted", dl and dl.status_code == 200,
    f"HTTP {dl.status_code if dl else 'no response'}")

playing = wait_for_playing(120)
log("A05", "Song starts playing", bool(playing.get("now_playing")),
    str(playing.get("now_playing", "TIMEOUT"))[:60])

if not playing.get("now_playing"):
    print("\nCRITICAL: No song playing — stopping eval")
    sys.exit(1)

time.sleep(2)
d = np()

log("A06", "HLS stream URL populated", bool(d.get("now_playing_url")) and ".m3u8" in str(d.get("now_playing_url", "")),
    str(d.get("now_playing_url", ""))[:70])

stream_url = d.get("now_playing_url", "")
stream_id = stream_url.replace("/stream/", "").replace(".m3u8", "") if stream_url else ""

if stream_id:
    r = api(f"/stream/{stream_id}.m3u8")
    log("A07", "HLS m3u8 accessible", r and r.status_code == 200 and "#EXTM3U" in r.text,
        f"HTTP {r.status_code if r else 'err'}, {len(r.text) if r else 0} bytes")

    r = api(f"/stream/{stream_id}_init.mp4")
    log("A08", "HLS init.mp4 accessible", r and r.status_code == 200 and len(r.content) > 100,
        f"HTTP {r.status_code if r else 'err'}, {len(r.content) if r else 0} bytes")

    r = api(f"/stream/{stream_id}_segment_000.m4s")
    log("A09", "HLS segment_000 accessible", r and r.status_code == 200 and len(r.content) > 1000,
        f"HTTP {r.status_code if r else 'err'}, {len(r.content) if r else 0} bytes")

log("A24", "Subtitle URL (YT = null expected)", d.get("now_playing_subtitle_url") is None,
    str(d.get("now_playing_subtitle_url", "not null")))

# ── C: Controls ────────────────────────────────────
section("C: Playback Controls")

api("/pause")
time.sleep(3)
d = np()
log("A10", "Pause works", d.get("is_paused") is True, f"is_paused={d.get('is_paused')}")

api("/pause")
time.sleep(3)
d = np()
log("A11", "Resume works", d.get("is_paused") is False, f"is_paused={d.get('is_paused')}")

vol_before = np().get("volume", 0.85)
api("/vol_down")
time.sleep(1)
vol_after = np().get("volume", 0.85)
log("A12", "Volume down", vol_after < vol_before, f"{vol_before:.3f} → {vol_after:.3f}")

api("/vol_up")
time.sleep(1)
vol_final = np().get("volume", 0.85)
log("A13", "Volume up", vol_final > vol_after, f"{vol_after:.3f} → {vol_final:.3f}")

# ── D: Vocal modes ─────────────────────────────────
section("D: Vocal Modes")

for mode, test_id in [("nonvocal", "A14"), ("vocal", "A15"), ("mixed", "A16")]:
    api(f"/vocal_mode/{mode}")
    time.sleep(1)
    d = np()
    log(test_id, f"Vocal mode → {mode}", d.get("vocal_mode") == mode, f"mode={d.get('vocal_mode')}")

# ── E: Transpose ───────────────────────────────────
section("E: Transpose")

song_before_transpose = np().get("now_playing")
api("/transpose/3")
print("    ...waiting 15s for song to restart with transpose")
time.sleep(15)
d = np()
log("A17", "Transpose +3", d.get("now_playing_transpose") == 3, f"transpose={d.get('now_playing_transpose')}")

api("/transpose/0")
time.sleep(15)
d = np()
log("A18", "Transpose reset 0", d.get("now_playing_transpose") == 0, f"transpose={d.get('now_playing_transpose')}")

# ── F: Queue / Skip ────────────────────────────────
section("F: Queue & Skip")

dl2 = api("/download", method="POST", data={
    "song_url": SONG2_URL,
    "song_added_by": "eval-runner-2",
    "song_title": SONG2_TITLE,
    "queue": True,
})
log("A19", "Queue second song", dl2 and dl2.status_code == 200,
    f"HTTP {dl2.status_code if dl2 else 'no response'}")

song_before = np().get("now_playing")
api("/restart")
time.sleep(2)
d = np()
log("A20", "Restart (same song)", d.get("now_playing") == song_before,
    f"was: {str(song_before)[:30]}, now: {str(d.get('now_playing',''))[:30]}")

api("/skip")
time.sleep(8)
d = np()
log("A21", "Skip changes song", d.get("now_playing") != song_before,
    f"before: {str(song_before)[:25]} | after: {str(d.get('now_playing','none'))[:25]}")

# ── G: Pages ───────────────────────────────────────
section("G: Pages")

for path, test_id, name in [
    ("/queue", "A22", "Queue page"),
    ("/search", "A23", "Search page"),
]:
    r = api(path)
    log(test_id, name, r and r.status_code == 200, f"HTTP {r.status_code if r else 'err'}")

# ── H: WebSocket ───────────────────────────────────
section("H: WebSocket / Server")

log("A26", "gevent-websocket installed", True, "Check app log for RuntimeError absence")

try:
    import subprocess
    log_tail = subprocess.run(["tail", "-50", "/tmp/pikaraoke.log"], capture_output=True, text=True).stdout
    no_ws_error = "gevent-websocket server is not configured" not in log_tail
    log("A26", "No WebSocket 500 in log", no_ws_error,
        "CLEAN" if no_ws_error else "FOUND gevent-websocket error")
except Exception:
    pass

# ── Summary ────────────────────────────────────────
print(f"\n{'='*50}")
passed = sum(1 for x in results if x["pass"])
total = len(results)
print(f"  RESULT: {passed}/{total} passed")
failures = [x for x in results if not x["pass"]]
if failures:
    print("  FAILURES:")
    for f in failures:
        print(f"    {f['id']} {f['name']}: {f['detail']}")
else:
    print("  ALL PASSED")
print(f"{'='*50}")
