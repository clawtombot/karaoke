# Research: TV Casting & Display for Home Karaoke
**Date:** 2026-03-18
**Status:** Open — implementation not started
**Intent:** Replace the current "open /splash in a TV browser" workaround with proper casting support that works from the phone UI with zero friction

---

## Problem Statement

Right now the `/splash` page is the TV display — fullscreen video + lyrics synchronized via SocketIO. Getting it onto a TV requires:
- Manually opening a browser on the TV and typing the server URL, OR
- Casting a browser tab from a laptop (Chrome → Cast Tab → pick Chromecast)

Neither works well in practice. A proper karaoke night needs: **phone → one tap → video appears on TV**. No browser, no URL to type.

---

## Landscape: What Actually Exists in 2026

### 1. Google Cast / Chromecast — **Best Fit**
**Protocol:** Google Cast Application Framework v3 (CAFv3)
**How it works:**
- A **Cast Receiver app** (HTML/JS) runs on the Chromecast, renders video fullscreen
- A **Cast Sender** button in the phone UI initiates the session
- The receiver fetches the HLS stream directly from the Flask server — no relay needed
- Media controls (pause/skip/volume) route through the Cast session

**Requirements to ship:**
- Register a Cast Application ID in the [Google Cast SDK Developer Console](https://cast.google.com/publish)
- Host a publicly accessible receiver HTML page (or use a local network workaround)
- Add Google Cast Sender JS SDK to the phone UI

**Receiver is just an HTML page:**
```html
<script src="https://www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js"></script>
<script>
  const ctx = cast.framework.CastReceiverContext.getInstance();
  ctx.start();
</script>
```
The receiver URL can be served from the Flask app itself (`/cast-receiver`). But Google requires HTTPS for the receiver — could use a self-signed cert or a free cert via Tailscale/Caddy.

**Local network workaround:** Use the "Default Media Web Receiver" (App ID `CC1AD845`) which accepts custom HLS URLs without needing to register a custom app. The sender just loads the M3U8 URL into it.

**Sender SDK in phone UI:**
```html
<script src="https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1"></script>
```
This adds the standard Cast button to Chrome-based browsers (including Android Chrome on the phone UI).

**Verdict:** Best option for Chromecast users. Zero server infrastructure needed — the Chromecast pulls HLS directly from Flask. The only friction is registering an App ID (free).

**Devices covered:** All Chromecasts, Chromecast with Google TV, Android TV, Google TV smart TVs (Sony, TCL, Hisense), Nest Hub, some Samsung/LG with Google TV.

---

### 2. DLNA / UPnP — **Broadest TV Coverage, No App Needed**
**Protocol:** UPnP AV / DLNA (Digital Living Network Alliance)
**How it works:**
- Flask server advertises as a UPnP MediaServer on the local network (via mDNS/SSDP)
- TV's built-in DLNA client discovers it and can browse/play
- OR: Flask sends a `SetAVTransportURI` command to the TV (MediaRenderer), pushing the HLS URL directly

**Python libraries:**
- `Cohen3` — full Python 3 DLNA MediaServer/MediaRenderer implementation
- `nano-dlna` — lightweight, can push a URL to any DLNA renderer
- `dlnap` — minimal, push-play to DLNA device with one command
- `dlna-cast` — uses ffmpeg + UPnP to cast HLS to renderers

**Rough integration:**
```python
import dlnap
devices = dlnap.discover(timeout=3)
devices[0].set_current_media(url="http://192.168.x.x:5555/stream/abc.m3u8")
devices[0].play()
```

**Verdict:** Covers the widest range of TVs (Samsung, LG, Sony, Philips, Panasonic — basically all smart TVs made since 2012 have DLNA). No app registration, no HTTPS required. Lower polish than Cast but universal.

**Gap:** No auto-discovery UI in the phone browser — requires a "Choose TV" flow in the Flask UI.

---

### 3. Roku — **Excellent for Dedicated Karaoke Setup**
**Protocol:** Roku sideloaded channel (BrightScript) + Direct Publisher / ECP
**How it works:**
- Sideload a custom BrightScript channel that knows to fetch from the Flask server
- Roku's External Control Protocol (ECP) lets you launch the channel and pass parameters (including HLS URL) from the phone UI via HTTP

**Minimal BrightScript channel:**
```brightscript
url = "http://192.168.x.x:5555/stream/{id}.m3u8"
video = CreateObject("roVideoScreen")
video.SetContent({ url: url, streamFormat: "hls" })
video.Show()
```

**ECP to launch from Flask:**
```
POST http://{roku-ip}:8060/launch/{channel-id}?contentId={stream-id}
```

**Verdict:** If someone has a Roku this is a great path — dedicated device, HLS native, no browser needed. Channel only needs to be sideloaded once. ECP control from Flask is trivial.

---

### 4. Fire TV / Android TV — **Easy via Existing Cast Apps OR Custom APK**
**Options:**
1. **Third-party apps** (Web Video Cast, TV Cast for Fire TV) — user installs once, then Flask sends an M3U8 URL to the app's "cast" endpoint. Low dev effort.
2. **Custom Android TV APK** — minimal Android app that opens an ExoPlayer pointed at the Flask HLS URL. Distributed via ADB sideload.
3. **Matter Casting** (2025 spec) — Amazon Fire TV OS 7+ supports it; not enough ecosystem tooling yet.

**Verdict:** Third-party approach has zero dev effort but depends on the user having a specific app installed. Custom APK is ~50 lines of Kotlin but requires ADB sideload once.

---

### 5. AirPlay — **Not the Right Fit**
AirPlay 2 is screen mirroring from iOS/macOS to a receiver. It's not a "push a URL to the TV" protocol — the sender's screen is encoded and transmitted. For karaoke we want the TV to fetch directly from the server (lower latency, higher quality, no battery drain on the phone).

UxPlay can turn a Linux box into an AirPlay target, but that's an extra device, not the TV itself. Skip.

---

### 6. Matter Casting — **Watch, Not Act**
The Matter 1.5 spec (Nov 2025) includes a Casting API. Amazon Fire TV, some TCL/Hisense TVs are early adopters. Promising as a universal open alternative to Google Cast, but:
- No Python/Flask library exists yet
- Requires devices to be Matter-certified
- Ecosystem is still forming

Revisit in 2027.

---

## Recommended Implementation Roadmap

### Phase 1 — DLNA Push (covers all smart TVs, minimal code)
**Scope:** Add a "Cast to TV" button in home.html. Flask discovers DLNA renderers on the LAN and pushes the current HLS stream URL to the selected one.

**Stack:**
- `nano-dlna` or `dlnap` Python library in Flask
- New route: `GET /cast/discover` → returns JSON list of DLNA devices
- New route: `POST /cast/play` → body `{device_id, stream_url}` → pushes HLS to renderer
- Home.html: "Cast" icon button → dropdown of discovered TVs → tap → done

**Effort:** ~1 day
**Coverage:** All DLNA-enabled smart TVs (vast majority of market)

---

### Phase 2 — Google Cast Sender (Chromecast + Android TV + Google TV)
**Scope:** Add a standard Cast button to the phone UI. On tap, opens a Cast session and loads the HLS stream into the Chromecast's Default Media Web Receiver.

**Stack:**
- Add Cast Sender SDK `<script>` to `base.html`
- Register once in Google Cast Developer Console (free, get an App ID)
- OR use Default Media Receiver (App ID `CC1AD845`) — no registration needed but no custom UI
- The Chromecast pulls HLS directly from Flask — no relay server

**Effort:** ~half day (Default Media Receiver path = almost zero code)
**Coverage:** All Chromecast devices, Chromecast with Google TV, Android TV

---

### Phase 3 — Roku ECP (dedicated setup)
**Scope:** One-time sideload of a BrightScript channel. Flask sends ECP launch commands with the current stream URL.

**Effort:** ~1 day (BrightScript channel + Flask ECP route)
**Coverage:** All Roku devices

---

## Open Questions / Assumptions to Validate

1. **HTTPS requirement for Cast Receiver:** Google Cast Receiver must be served over HTTPS. Flask runs HTTP on the LAN. Workaround options: Tailscale HTTPS, Caddy reverse proxy, or use Default Media Receiver (no custom receiver needed).

2. **DLNA HLS support varies:** Some older DLNA renderers don't support HLS natively — they expect plain MP4 or MPEG-TS. May need to offer the progressive MP4 URL (`/stream/{id}.mp4`) as fallback.

3. **Local network discovery in browser:** The Cast Sender SDK works in Chrome desktop and Android Chrome. It does NOT work in Firefox, Safari, or PWAs. The DLNA path works anywhere since it's server-side.

4. **SocketIO sync for Cast Receiver:** The current `/splash` page handles pause/skip/vocal-mode changes via SocketIO. A Cast Receiver would need the same SocketIO connection. Since the receiver is also a web page, this should work as-is.

---

## References

| Resource | URL |
|----------|-----|
| Google Cast CAFv3 Receiver docs | https://developers.google.com/cast/docs/web_receiver/basic |
| Google Cast Sender web integration | https://developers.google.com/cast/docs/web_sender/integrate |
| Default Media Web Receiver (no registration) | App ID: `CC1AD845` |
| nano-dlna Python library | https://github.com/gabrielmagno/nano-dlna |
| dlnap Python library | https://github.com/ttyridal/dlnap |
| Roku ECP docs | https://developer.roku.com/docs/developer-program/dev-tools/external-control-api.md |
| Matter Casting spec overview | https://www.matteralpha.com/explainer/what-is-matter-casting |
| UxPlay (AirPlay2 receiver) | https://github.com/antimof/UxPlay |
| FCast open protocol | https://fcast.org |
| WHIP RFC 9725 (WebRTC ingestion) | https://datatracker.ietf.org/doc/rfc9725/ |

---

## Why NOT Just "Open the Splash URL on the TV"

- Requires the user to know the server IP
- Requires the TV to have a usable browser (not all do)
- No auto-reconnect if the server restarts
- No discovery — user must type the URL
- Breaks the "phone as remote" mental model

The goal is: song starts → phone vibrates with "Cast to TV?" → tap → Freddie Mercury appears on the screen. Zero friction.
