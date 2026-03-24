/**
 * Web Audio API stem mixer — replaces the old HTMLAudioElement approach.
 * Uses AudioContext + GainNode per stem for sample-accurate sync and volume control.
 */

export const STEM_NAMES = ['drums', 'bass', 'other', 'vocals', 'guitar', 'piano'] as const;
export type StemName = (typeof STEM_NAMES)[number];

interface StemChannel {
	source: AudioBufferSourceNode | null;
	gain: GainNode;
	buffer: AudioBuffer | null;
	loaded: boolean;
}

let ctx: AudioContext | null = null;
let channels: Map<StemName, StemChannel> = new Map();
let masterGain: GainNode | null = null;
let playing = false;
let startTime = 0; // AudioContext time when playback started
let startOffset = 0; // Song position offset
let readyCallbacks: Array<() => void> = [];

export function isActive(): boolean {
	return playing && channels.size > 0;
}

/** Whether the AudioContext is usable (not suspended by autoplay policy). */
export function isReady(): boolean {
	return ctx?.state === 'running';
}

/** Initialize the audio context and gain nodes. */
export function init() {
	if (ctx) {
		// Already initialized — try to resume (needs user gesture context)
		if (ctx.state === 'suspended') {
			ctx.resume().catch(() => {});
		}
		return;
	}
	ctx = new AudioContext();
	masterGain = ctx.createGain();
	masterGain.connect(ctx.destination);

	for (const name of STEM_NAMES) {
		const gain = ctx.createGain();
		gain.connect(masterGain);
		channels.set(name, { source: null, gain, buffer: null, loaded: false });
	}

	// Fire ready callbacks when AudioContext transitions to 'running'
	ctx.onstatechange = () => {
		if (ctx?.state === 'running' && readyCallbacks.length > 0) {
			const cbs = [...readyCallbacks];
			readyCallbacks = [];
			for (const cb of cbs) cb();
		}
	};

	if (ctx.state === 'suspended') {
		ctx.resume().catch(() => {});
	}
}

/** Register a callback for when AudioContext becomes ready. Fires immediately if already running. */
export function onReady(cb: () => void) {
	if (ctx?.state === 'running') {
		cb();
	} else {
		readyCallbacks.push(cb);
	}
}

/** Load stem audio files from URLs. */
export async function loadStems(stemUrls: Record<string, string>): Promise<boolean> {
	if (!ctx || !masterGain) init();
	if (!ctx) return false;

	const loadPromises = Object.entries(stemUrls).map(async ([name, url]) => {
		const ch = channels.get(name as StemName);
		if (!ch) return;
		try {
			const response = await fetch(url);
			const arrayBuffer = await response.arrayBuffer();
			ch.buffer = await ctx!.decodeAudioData(arrayBuffer);
			ch.loaded = true;
		} catch (e) {
			console.error(`[stem-mixer] Failed to load ${name}:`, e);
			ch.loaded = false;
		}
	});

	await Promise.all(loadPromises);
	const loadedCount = [...channels.values()].filter((ch) => ch.loaded).length;
	console.log(`[stem-mixer] Loaded ${loadedCount}/${STEM_NAMES.length} stems`);
	return loadedCount > 0;
}

/** Start playback of all loaded stems at the given offset. */
export function play(offset: number = 0) {
	if (!ctx || !masterGain) return;
	stop(); // Stop any existing playback

	startOffset = offset;
	startTime = ctx.currentTime;

	for (const [name, ch] of channels) {
		if (!ch.buffer) continue;
		const source = ctx.createBufferSource();
		source.buffer = ch.buffer;
		source.connect(ch.gain);
		source.start(0, offset);
		ch.source = source;
	}
	playing = true;
}

/** Stop all stem playback. */
export function stop() {
	for (const ch of channels.values()) {
		if (ch.source) {
			try {
				ch.source.stop();
			} catch (_) {
				/* already stopped */
			}
			ch.source = null;
		}
	}
	playing = false;
}

/** Sync stems to a video element's current time. */
export function syncToVideo(videoTime: number) {
	if (!ctx || !playing) return;
	const stemTime = getCurrentTime();
	const drift = Math.abs(stemTime - videoTime);

	if (drift > 0.15) {
		// Re-sync by restarting from video position
		play(videoTime);
	}
}

/** Get current playback position. */
export function getCurrentTime(): number {
	if (!ctx || !playing) return 0;
	return startOffset + (ctx.currentTime - startTime);
}

/** Set volume for a specific stem (0-1). */
export function setStemVolume(stem: StemName, volume: number) {
	const ch = channels.get(stem);
	if (ch) {
		ch.gain.gain.setTargetAtTime(volume, ctx?.currentTime ?? 0, 0.02);
	}
}

/** Toggle a stem on/off. */
export function toggleStem(stem: StemName, enabled: boolean, volume: number = 1) {
	setStemVolume(stem, enabled ? volume : 0);
}

/** Apply a full mix state. */
export function applyMix(mix: Record<string, boolean>, volume: number = 1) {
	for (const [stem, enabled] of Object.entries(mix)) {
		toggleStem(stem as StemName, enabled, volume);
	}
}

/** Set master volume. */
export function setMasterVolume(volume: number) {
	if (masterGain && ctx) {
		masterGain.gain.setTargetAtTime(volume, ctx.currentTime, 0.02);
	}
	// Also update individual stem volumes for mix state
	for (const [name, ch] of channels) {
		if (ch.gain) {
			// Only adjust stems that are "on" in the mix
			// The gain was already set by applyMix
		}
	}
}

/** Pause stem audio. */
export function pause() {
	if (!ctx || !playing) return;
	startOffset = getCurrentTime();
	stop();
}

/** Resume from paused position. */
export function resume() {
	if (!ctx) return;
	play(startOffset);
}

/** Teardown — release all resources. */
export function teardown() {
	stop();
	channels.clear();
	readyCallbacks = [];
	if (ctx) {
		ctx.close();
		ctx = null;
	}
	masterGain = null;
}
