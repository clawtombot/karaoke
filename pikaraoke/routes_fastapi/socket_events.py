"""Socket.IO event handlers for HomeKaraoke (python-socketio ASGI)."""

import logging

from pikaraoke.lib.dependencies import get_karaoke

# Track connected splash screen clients and the elected master
splash_connections: set[str] = set()
master_splash_id: str | None = None


def setup_socket_events(sio) -> None:
    """Register Socket.IO event handlers on the AsyncServer."""

    @sio.on("end_song")
    async def end_song(sid, reason: str) -> None:
        k = get_karaoke()
        k.playback_controller.end_song(reason)

    @sio.on("start_song")
    async def start_song(sid) -> None:
        k = get_karaoke()
        k.playback_controller.start_song()

    @sio.on("clear_notification")
    async def clear_notification(sid) -> None:
        k = get_karaoke()
        k.reset_now_playing_notification()

    @sio.on("register_splash")
    async def register_splash(sid) -> None:
        global master_splash_id
        splash_connections.add(sid)
        logging.info(f"Splash screen registered: {sid}")

        if master_splash_id is None or master_splash_id == sid:
            master_splash_id = sid
            await sio.emit("splash_role", "master", room=sid)
            logging.info(f"Master splash assigned: {sid}")
        else:
            await sio.emit("splash_role", "slave", room=sid)
            logging.info(f"Slave splash assigned: {sid}")

    @sio.on("lyrics_offset")
    async def handle_lyrics_offset(sid, offset_ms: int) -> None:
        """Relay lyrics timing offset to all clients (especially splash)."""
        await sio.emit("lyrics_offset", offset_ms, skip_sid=sid)

    @sio.on("pitch_offset")
    async def handle_pitch_offset(sid, offset_sec: float) -> None:
        """Relay pitch graph timing offset to all clients."""
        await sio.emit("pitch_offset", offset_sec, skip_sid=sid)

    @sio.on("pitch_noise_gate")
    async def handle_pitch_noise_gate(sid, gate: float) -> None:
        """Relay pitch noise gate threshold to all clients."""
        await sio.emit("pitch_noise_gate", gate, skip_sid=sid)

    @sio.on("backing_noise_gate")
    async def handle_backing_noise_gate(sid, gate: float) -> None:
        """Relay backing vocal noise gate threshold to all clients."""
        await sio.emit("backing_noise_gate", gate, skip_sid=sid)

    @sio.on("pitch_merge_gap")
    async def handle_pitch_merge_gap(sid, gap: float) -> None:
        """Relay pitch note merge gap threshold to all clients."""
        await sio.emit("pitch_merge_gap", gap, skip_sid=sid)

    @sio.on("pitch_merge_semitones")
    async def handle_pitch_merge_semitones(sid, semitones: float) -> None:
        """Relay pitch vertical merge (semitone tolerance) to all clients."""
        await sio.emit("pitch_merge_semitones", semitones, skip_sid=sid)

    @sio.on("stem_toggle")
    async def handle_stem_toggle(sid, stem: str) -> None:
        k = get_karaoke()
        if k.toggle_stem(stem):
            await sio.emit("stem_mix_update", k.stem_mix)

    @sio.on("stem_volume")
    async def handle_stem_volume(sid, data: dict) -> None:
        k = get_karaoke()
        stem = data.get("stem", "")
        volume = float(data.get("volume", 1.0))
        if k.set_stem_volume(stem, volume):
            await sio.emit("stem_mix_update", k.stem_mix)

    @sio.on("playback_position")
    async def handle_playback_position(sid, position: float) -> None:
        global master_splash_id
        if sid == master_splash_id:
            k = get_karaoke()
            k.playback_controller.now_playing_position = position
            await sio.emit("playback_position", position, skip_sid=sid)

    @sio.on("disconnect")
    async def handle_disconnect(sid) -> None:
        global master_splash_id
        if sid in splash_connections:
            splash_connections.remove(sid)
            logging.info(f"Splash screen disconnected: {sid}")
            if sid == master_splash_id:
                master_splash_id = None
                logging.info("Master splash disconnected, electing new master")
                if splash_connections:
                    new_master = next(iter(splash_connections))
                    master_splash_id = new_master
                    await sio.emit("splash_role", "master", room=new_master)
                    logging.info(f"New master splash elected: {new_master}")
