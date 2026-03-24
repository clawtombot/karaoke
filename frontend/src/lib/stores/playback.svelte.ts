/**
 * Playback state store — synced via Socket.IO now_playing events.
 * Central source of truth for what's playing, queue state, stem mix, etc.
 */

export interface NowPlaying {
	now_playing: string | null;
	now_playing_user: string | null;
	now_playing_duration: number | null;
	now_playing_transpose: number;
	now_playing_url: string | null;
	now_playing_file: string | null;
	now_playing_subtitle_url: string | null;
	now_playing_position: number | null;
	is_paused: boolean;
	up_next: string | null;
	next_user: string | null;
	volume: number;
	vocal_splitter_enabled: boolean;
	stems_available: boolean;
	stem_urls: Record<string, string> | null;
	stem_mix: Record<string, boolean>;
	stem_progress: { ready: number; total: number; error: boolean } | null;
	boot_id: string;
}

const DEFAULT_STATE: NowPlaying = {
	now_playing: null,
	now_playing_user: null,
	now_playing_duration: null,
	now_playing_transpose: 0,
	now_playing_url: null,
	now_playing_file: null,
	now_playing_subtitle_url: null,
	now_playing_position: null,
	is_paused: true,
	up_next: null,
	next_user: null,
	volume: 0.85,
	vocal_splitter_enabled: false,
	stems_available: false,
	stem_urls: null,
	stem_mix: {},
	stem_progress: null,
	boot_id: '',
};

// Reactive state
let state: NowPlaying = $state({ ...DEFAULT_STATE });

/** Update the full now-playing state (called from socket event). */
export function update(np: NowPlaying) {
	// Merge into existing state to preserve reactivity
	Object.assign(state, np);
}

/** Update just the stem mix (called from stem_mix_update event). */
export function updateStemMix(mix: Record<string, boolean>) {
	state.stem_mix = mix;
}

/** Get the current state (reactive). */
export function getState(): NowPlaying {
	return state;
}

/** Reset to defaults. */
export function reset() {
	Object.assign(state, DEFAULT_STATE);
}

/** Fetch initial state from API. */
export async function fetchNowPlaying() {
	try {
		const { base } = await import('$app/paths');
		const res = await fetch(`${base}/now_playing`);
		if (res.ok) {
			const data = await res.json();
			update(data);
		}
	} catch (e) {
		console.error('[playback] failed to fetch now_playing:', e);
	}
}
