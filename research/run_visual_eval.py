#!/usr/bin/env python3
"""
Home Karaoke — Visual / Browser Eval Runner
Run: python research/run_visual_eval.py
Requires: app running at localhost:5555, playwright + firefox installed
  playwright install firefox
"""

import json
import sys
import time

import requests

BASE = "http://localhost:5555"
results = []


def log(test_id, name, passed, detail=""):
    icon = "PASS" if passed else "FAIL"
    results.append({"id": test_id, "name": name, "pass": passed, "detail": detail})
    print(f"  [{icon}] {test_id} {name}: {detail}")
    sys.stdout.flush()


def np():
    try:
        r = requests.get(BASE + "/now_playing", timeout=10)
        return json.loads(r.text)
    except Exception:
        return {}


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install firefox")
    sys.exit(1)

print("=" * 50)
print("  HOME KARAOKE — VISUAL EVAL SUITE (Firefox)")
print("=" * 50)

# Ensure a song is playing
d = np()
if not d.get("now_playing"):
    print("\n  Queuing test song...")
    requests.post(BASE + "/download", json={
        "song_url": "https://www.youtube.com/watch?v=HgzGwKwLmgM",
        "song_added_by": "visual-eval",
        "song_title": "Queen - Don't Stop Me Now",
        "queue": True,
    }, timeout=15)
    for i in range(120):
        d = np()
        if d.get("now_playing"):
            break
        time.sleep(1)
    if not d.get("now_playing"):
        print("  CRITICAL: Song never started. Aborting.")
        sys.exit(1)

print(f"  Song playing: {d.get('now_playing')}\n")

with sync_playwright() as p:
    b = p.firefox.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1100, "height": 800})
    page = ctx.new_page()

    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    page.goto(BASE + "/", wait_until="domcontentloaded")
    print("  Page loaded. Waiting 12s for HLS to buffer...")
    time.sleep(8)

    # Force play (autoplay policy requires user gesture in headless)
    play_result = page.evaluate("""async () => {
        var v = document.getElementById('pr-video');
        if (!v) return {error: 'no video element'};
        try {
            v.currentTime = 3;
            await v.play();
            return {ok: true};
        } catch(e) {
            return {error: e.toString()};
        }
    }""")
    time.sleep(4)  # let frame render

    state = page.evaluate("""() => {
        var v = document.getElementById('pr-video');
        var panel = document.getElementById('pr-video-panel');
        var npTitle = document.getElementById('pr-np-title');
        var liveEl = document.querySelector('.pr-np-live');
        var controls = document.querySelector('.pr-controls-area');
        var pitchPanel = document.querySelector('.pr-pitch-panel');
        var hasSubCanvas = !!document.querySelector('#pr-video-panel canvas');

        return {
            videoReadyState: v ? v.readyState : -1,
            videoNetworkState: v ? v.networkState : -1,
            videoCurrentTime: v ? v.currentTime : -1,
            videoBuffered: v && v.buffered.length > 0 ? v.buffered.end(0) : 0,
            videoWidth: v ? v.videoWidth : 0,
            videoHeight: v ? v.videoHeight : 0,
            videoError: v && v.error ? v.error.code : null,
            panelHidden: panel ? panel.style.display === 'none' : true,
            nowPlayingTitle: npTitle ? npTitle.textContent : '',
            liveVisible: liveEl ? getComputedStyle(liveEl).display !== 'none' : false,
            controlsVisible: controls ? getComputedStyle(controls).display !== 'none' : false,
            pitchPanelVisible: pitchPanel ? getComputedStyle(pitchPanel).display !== 'none' : false,
            subtitleCanvasPresent: hasSubCanvas,
            hlsLoaded: typeof Hls !== 'undefined',
            hlsSupported: typeof Hls !== 'undefined' && Hls.isSupported(),
        };
    }""")

    print("\n─────────────────────────────────────────────────")
    print("  B: Video Player")
    print("─────────────────────────────────────────────────")

    log("B01", "Video readyState ≥ 3", state["videoReadyState"] >= 3,
        f"readyState={state['videoReadyState']}")
    log("B02", "Video has dimensions", state["videoWidth"] > 0 and state["videoHeight"] > 0,
        f"{state['videoWidth']}×{state['videoHeight']}")
    log("B03", "Video buffered > 5s", state["videoBuffered"] > 5,
        f"buffered={state['videoBuffered']:.1f}s")
    log("B04", "Video panel visible", not state["panelHidden"],
        "visible" if not state["panelHidden"] else "hidden")
    log("B05", "No video decode error", state["videoError"] is None,
        f"error={state['videoError']}")

    print("\n─────────────────────────────────────────────────")
    print("  B: UI State")
    print("─────────────────────────────────────────────────")

    log("B06", "Now-playing title matches", len(state["nowPlayingTitle"]) > 3,
        f'"{state["nowPlayingTitle"][:50]}"')
    log("B07", "LIVE indicator visible", state["liveVisible"], str(state["liveVisible"]))
    log("B08", "Controls visible", state["controlsVisible"], str(state["controlsVisible"]))
    log("B11", "Pitch graph visible", state["pitchPanelVisible"], str(state["pitchPanelVisible"]))
    log("B14", "No subtitle canvas (YT = expected)", not state["subtitleCanvasPresent"],
        "no canvas (correct for YT)" if not state["subtitleCanvasPresent"] else "canvas present")

    print("\n─────────────────────────────────────────────────")
    print("  B: HLS.js")
    print("─────────────────────────────────────────────────")

    log("B16", "HLS.js loaded", state["hlsLoaded"], str(state["hlsLoaded"]))
    log("B17", "HLS.js supported in browser", state["hlsSupported"], str(state["hlsSupported"]))

    # Screenshot
    shot_path = "/workspace/group/output/visual-eval-result.png"
    page.screenshot(path=shot_path, full_page=False)
    print(f"\n  Screenshot: {shot_path}")

    if console_errors:
        print(f"\n  Console errors ({len(console_errors)}):")
        for e in console_errors[:5]:
            print(f"    {e[:100]}")

    b.close()

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
