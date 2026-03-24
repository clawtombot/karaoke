/**
 * Lyrics store — manages word-timed lyrics data and current highlight position.
 */
import { base } from '$app/paths';
import { emit } from '$lib/stores/socket.svelte';

export interface LyricsWord {
	start: number; // ms
	end: number; // ms
	text: string;
}

export interface LyricsLine {
	start: number; // ms
	end: number; // ms
	text: string;
	romanized: string | null;
	translated: string | null;
	words: LyricsWord[] | null;
}

export interface SongLyrics {
	source: string;
	language: string;
	lines: LyricsLine[];
	has_word_timing: boolean;
	has_romanization: boolean;
	has_translation: boolean;
}

// Reactive state
let lyrics: SongLyrics | null = $state(null);
let currentLineIndex = $state(-1);
let currentWordIndex = $state(-1);
let wordProgress = $state(0); // 0-1 progress within active word
let loading = $state(false);
let error: string | null = $state(null);
let offsetMs = $state(0); // User-adjustable timing offset (ms)
let currentStreamUid = ''; // Track current song for offset persistence

// Per-song offset storage (localStorage)
const OFFSET_KEY = 'lyrics_offsets';
function loadOffset(uid: string): number {
	try {
		const stored = localStorage.getItem(OFFSET_KEY);
		if (stored) {
			const map = JSON.parse(stored);
			return map[uid] ?? 0;
		}
	} catch {}
	return 0;
}
function saveOffset(uid: string, ms: number) {
	try {
		const stored = localStorage.getItem(OFFSET_KEY);
		const map = stored ? JSON.parse(stored) : {};
		if (ms === 0) { delete map[uid]; } else { map[uid] = ms; }
		localStorage.setItem(OFFSET_KEY, JSON.stringify(map));
	} catch {}
}

/** Load lyrics for a stream. */
export async function loadLyrics(streamUid: string) {
	loading = true;
	error = null;
	lyrics = null;
	currentLineIndex = -1;
	currentWordIndex = -1;
	currentStreamUid = streamUid;
	offsetMs = loadOffset(streamUid);

	try {
		const res = await fetch(`${base}/api/lyrics/${streamUid}`);
		if (res.ok) {
			lyrics = await res.json();
		} else if (res.status === 404) {
			lyrics = null; // No lyrics available — graceful
		} else {
			error = `Failed to load lyrics: ${res.status}`;
		}
	} catch (e) {
		error = `Lyrics fetch error: ${e}`;
	} finally {
		loading = false;
	}
}

/** Update highlight position based on current playback time (called from rAF loop). */
export function updatePosition(currentMs: number) {
	if (!lyrics?.lines) return;

	// Apply user offset (positive = lyrics appear earlier)
	const adjusted = currentMs + offsetMs;

	// Find active line
	const lineIdx = lyrics.lines.findIndex(
		(l) => adjusted >= l.start && adjusted < l.end
	);
	currentLineIndex = lineIdx;

	if (lineIdx === -1) {
		currentWordIndex = -1;
		wordProgress = 0;
		return;
	}

	const line = lyrics.lines[lineIdx];
	if (!line.words || line.words.length === 0) {
		// Line-level only — estimate progress across whole line
		currentWordIndex = -1;
		wordProgress = (adjusted - line.start) / (line.end - line.start);
		return;
	}

	// Find active word within line
	const wIdx = line.words.findIndex(
		(w) => adjusted >= w.start && adjusted < w.end
	);
	currentWordIndex = wIdx;

	if (wIdx >= 0) {
		const word = line.words[wIdx];
		wordProgress = (adjusted - word.start) / (word.end - word.start);
	} else {
		wordProgress = 0;
	}
}

/** Clear lyrics state. */
export function clearLyrics() {
	lyrics = null;
	currentLineIndex = -1;
	currentWordIndex = -1;
	wordProgress = 0;
	error = null;
}

/** Adjust lyrics timing offset (ms). Positive = lyrics appear earlier. */
export function setOffset(ms: number, broadcast = true) {
	offsetMs = ms;
	saveOffset(currentStreamUid, ms);
	if (broadcast) emit('lyrics_offset', ms);
}

/** Apply offset from remote socket event (no re-broadcast). */
export function applyRemoteOffset(ms: number) {
	offsetMs = ms;
}
export function nudgeOffset(deltaMs: number) {
	setOffset(offsetMs + deltaMs);
}

/** Search for lyrics candidates from multiple sources. */
export interface LyricsCandidate {
	id: string;
	title: string;
	artist: string;
	source: string;
	album?: string;
	duration?: number;
}

export async function searchCandidates(title: string, artist: string): Promise<LyricsCandidate[]> {
	try {
		const params = new URLSearchParams({ title, artist });
		const res = await fetch(`${base}/api/lyrics/candidates?${params}`);
		if (res.ok) {
			const data = await res.json();
			return data.candidates ?? [];
		}
	} catch {}
	return [];
}

/** Select a specific lyrics candidate — fetches, saves to cache, notifies splash. */
export async function selectCandidate(candidateId: string): Promise<boolean> {
	loading = true;
	error = null;
	try {
		const res = await fetch(`${base}/api/lyrics/select`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ candidate_id: candidateId }),
		});
		if (res.ok) {
			lyrics = await res.json();
			currentLineIndex = -1;
			currentWordIndex = -1;
			return true;
		} else {
			error = 'Failed to load selected lyrics';
			return false;
		}
	} catch (e) {
		error = `Select failed: ${e}`;
		return false;
	} finally {
		loading = false;
	}
}

/** Reload lyrics for current stream (called when splash receives lyrics_reload event). */
export async function reloadLyrics() {
	if (currentStreamUid) {
		await loadLyrics(currentStreamUid);
	}
}

// Getters
export function getLyrics() { return lyrics; }
export function getCurrentLineIndex() { return currentLineIndex; }
export function getCurrentWordIndex() { return currentWordIndex; }
export function getWordProgress() { return wordProgress; }
export function isLoading() { return loading; }
export function getError() { return error; }
export function getOffset() { return offsetMs; }
