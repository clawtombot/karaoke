/**
 * Lyrics store — manages word-timed lyrics data and current highlight position.
 */
import { base } from '$app/paths';

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

/** Load lyrics for a stream. */
export async function loadLyrics(streamUid: string) {
	loading = true;
	error = null;
	lyrics = null;
	currentLineIndex = -1;
	currentWordIndex = -1;

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

	// Find active line
	const lineIdx = lyrics.lines.findIndex(
		(l) => currentMs >= l.start && currentMs < l.end
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
		wordProgress = (currentMs - line.start) / (line.end - line.start);
		return;
	}

	// Find active word within line
	const wIdx = line.words.findIndex(
		(w) => currentMs >= w.start && currentMs < w.end
	);
	currentWordIndex = wIdx;

	if (wIdx >= 0) {
		const word = line.words[wIdx];
		wordProgress = (currentMs - word.start) / (word.end - word.start);
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

// Getters
export function getLyrics() { return lyrics; }
export function getCurrentLineIndex() { return currentLineIndex; }
export function getCurrentWordIndex() { return currentWordIndex; }
export function getWordProgress() { return wordProgress; }
export function isLoading() { return loading; }
export function getError() { return error; }
