<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { base } from '$app/paths';
	import { getState, fetchNowPlaying } from '$lib/stores/playback.svelte';
	import { loadLyrics, clearLyrics, getLyrics, nudgeOffset as _nudgeOffset, getOffset, setOffset as _setOffset, searchCandidates, selectCandidate, type LyricsCandidate } from '$lib/stores/lyrics.svelte';

	function setOffset(ms: number) { _setOffset(ms); saveSongConfig(); }
	function nudgeOffset(ms: number) { _nudgeOffset(ms); saveSongConfig(); }
	import { on, emit } from '$lib/stores/socket.svelte';
	import LyricsPanel from '$components/LyricsPanel.svelte';
	import StemMixer from '$components/StemMixer.svelte';
	import TabBar from '$components/TabBar.svelte';

	const np = $derived(getState());
	const lyricsData = $derived(getLyrics());
	const lyricsOffset = $derived(getOffset());
	let currentTimeMs = $state(0);
	let volume = $state(0.85);

	// Pitch graph sync
	let pitchOffsetSec = $state(0);
	let pitchNoiseGate = $state(0.05);
	function setPitchOffset(sec: number) {
		pitchOffsetSec = sec;
		emit('pitch_offset', sec);
		saveSongConfig();
	}
	function setPitchNoiseGate(val: number) {
		pitchNoiseGate = Math.round(val * 100) / 100;
		emit('pitch_noise_gate', pitchNoiseGate);
		saveSongConfig();
	}

	// Persist offsets server-side per song
	let saveTimer: ReturnType<typeof setTimeout> | null = null;
	function saveSongConfig() {
		if (saveTimer) clearTimeout(saveTimer);
		saveTimer = setTimeout(() => {
			const file = np.now_playing_file;
			if (!file) return;
			fetch(api(`/api/song_config/${encodeURIComponent(file)}`), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					lyrics_offset_ms: lyricsOffset || null,
					pitch_offset_sec: pitchOffsetSec || null,
					noise_gate: pitchNoiseGate !== 0.05 ? pitchNoiseGate : null,
				}),
			}).catch(() => {});
		}, 500);
	}

	// Lyrics search
	let showLyricsSearch = $state(false);
	let searchTitle = $state('');
	let searchArtist = $state('');
	let searchLoading = $state(false);
	let candidates: LyricsCandidate[] = $state([]);
	let selectingId = $state('');

	async function doLyricsSearch() {
		if (!searchTitle.trim()) return;
		searchLoading = true;
		candidates = [];
		candidates = await searchCandidates(searchTitle.trim(), searchArtist.trim());
		searchLoading = false;
	}

	async function pickCandidate(id: string) {
		selectingId = id;
		const ok = await selectCandidate(id);
		selectingId = '';
		if (ok) {
			showLyricsSearch = false;
			// Keep candidates + query so user can reopen and pick a different one
		}
	}
	let transpose = $state(0);
	let isSeeking = $state(false);

	// Client-side time interpolation: sync from server, tick locally between updates
	let lastServerPos = 0;     // last known server position (seconds)
	let lastServerTime = 0;    // performance.now() when we received it
	let isPlaying = $state(false);
	let rafId: number | null = null;
	let seekCooldown = 0;      // ignore server sync until this timestamp

	function syncFromServer(positionSec: number) {
		if (isSeeking || performance.now() < seekCooldown) return;
		// Don't override paused state with stale position events
		if (np.is_paused) return;
		lastServerPos = positionSec;
		lastServerTime = performance.now();
		isPlaying = true;
	}

	function interpolationLoop() {
		if (isPlaying && !isSeeking && !np.is_paused && performance.now() >= seekCooldown) {
			const elapsed = (performance.now() - lastServerTime) / 1000;
			currentTimeMs = (lastServerPos + elapsed) * 1000;
		}
		rafId = requestAnimationFrame(interpolationLoop);
	}

	$effect(() => { volume = np.volume; });

	// Pause/resume tracking
	$effect(() => {
		if (np.is_paused) {
			isPlaying = false;
		}
	});

	let lastUrl: string | null = null;
	$effect(() => {
		const url = np.now_playing_url;
		if (url && url !== lastUrl) {
			lastUrl = url;
			initialSynced = false; // Re-sync position for new song
			const uid = url.split('/').pop()?.replace(/\.(m3u8|mp4)$/, '') ?? '';
			loadLyrics(uid);
			// Restore saved config for this song
			const file = np.now_playing_file;
			if (file) {
				fetch(api(`/api/song_config/${encodeURIComponent(file)}`))
					.then((r) => r.ok ? r.json() : {})
					.then((cfg) => {
						if (cfg.lyrics_offset_ms) _setOffset(cfg.lyrics_offset_ms, true);
						else _setOffset(0, false);
						pitchOffsetSec = cfg.pitch_offset_sec ?? 0;
						pitchNoiseGate = cfg.noise_gate ?? 0.05;
						emit('pitch_offset', pitchOffsetSec);
						emit('pitch_noise_gate', pitchNoiseGate);
					})
					.catch(() => {});
			} else {
				_setOffset(0, false);
				pitchOffsetSec = 0;
				pitchNoiseGate = 0.05;
			}
			// Clear search state for new song
			searchTitle = '';
			candidates = [];
		} else if (!url && lastUrl) {
			lastUrl = null;
			initialSynced = false;
			clearLyrics();
		}
	});

	// Sync from server position on initial load only
	let initialSynced = false;
	$effect(() => {
		if (!initialSynced && np.now_playing_position) {
			initialSynced = true;
			syncFromServer(np.now_playing_position);
		}
	});

	function formatTime(seconds: number): string {
		if (isNaN(seconds) || seconds < 0) return '0:00';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${m}:${String(s).padStart(2, '0')}`;
	}

	const progressPct = $derived(
		np.now_playing_duration ? Math.min(100, (currentTimeMs / 1000 / np.now_playing_duration) * 100) : 0
	);

	async function doSkip() { await fetch(api('/skip')); }
	let pausePending = false;
	async function doPause() {
		if (pausePending) return; // Debounce rapid taps
		pausePending = true;
		await fetch(api('/pause'));
		// Small cooldown to prevent double-toggle
		setTimeout(() => { pausePending = false; }, 300);
	}
	async function doRestart() { await fetch(api('/restart')); }
	async function setVolume(e: Event) {
		const val = (e.target as HTMLInputElement).value;
		volume = parseFloat(val);
		await fetch(api('/volume/') + val);
	}
	async function applyTranspose() {
		if (transpose !== 0 && confirm('Transpose ' + (transpose > 0 ? '+' : '') + transpose + '?')) {
			await fetch(api('/transpose/') + transpose);
			transpose = 0;
		}
	}
	async function toggleStem(stem: string) { await fetch(api('/stem_toggle/') + stem); }

	function seekStart(e: TouchEvent | MouseEvent) {
		isSeeking = true;
		seekMove(e);
	}

	function seekMove(e: TouchEvent | MouseEvent) {
		if (!isSeeking || !np.now_playing_duration) return;
		const track = (e.currentTarget as HTMLElement);
		const rect = track.getBoundingClientRect();
		const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
		const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
		currentTimeMs = ratio * np.now_playing_duration * 1000;
	}

	async function seekEnd() {
		if (!isSeeking) return;
		isSeeking = false;
		const pos = currentTimeMs / 1000;
		// Ignore server sync for 2s so stale position doesn't snap back
		seekCooldown = performance.now() + 2000;
		lastServerPos = pos;
		lastServerTime = performance.now();
		isPlaying = true;
		await fetch(api('/seek/') + pos);
	}

	let unsubs: Array<() => void> = [];

	onMount(() => {
		fetchNowPlaying();

		// Start interpolation loop for smooth lyrics scrolling
		interpolationLoop();

		// Listen for real-time position from master splash via socket
		unsubs = [
			on('playback_position', (position: any) => {
				if (!isSeeking) {
					syncFromServer(position);
				}
			}),
		];
	});
	onDestroy(() => {
		if (rafId) cancelAnimationFrame(rafId);
		unsubs.forEach((fn) => fn());
	});
</script>

<svelte:head><title>Remote — HomeKaraoke</title></svelte:head>

<div class="remote-root">
	{#if np.now_playing}
		<!-- Up next (slim banner at top) -->
		{#if np.up_next}
			<div class="up-next">
				<span class="up-next-label">NEXT</span>
				<span class="up-next-title">{np.up_next}</span>
				{#if np.next_user}<span class="up-next-singer">{np.next_user}</span>{/if}
			</div>
		{/if}

		<!-- Lyrics (album art replacement) -->
		<div class="lyrics-hero">
			<LyricsPanel {currentTimeMs} />
		</div>

		<!-- Song info -->
		<div class="song-info">
			<div class="song-title">{np.now_playing}</div>
			<div class="song-meta">
				<span class="song-artist">{np.now_playing_user ?? ''}</span>
				{#if lyricsData}
					<span class="meta-dot"></span>
					<span class="lyrics-source">{lyricsData.source}{lyricsData.has_word_timing ? '' : ' · estimated'}</span>
				{/if}
			</div>
		</div>

		<!-- Lyrics controls -->
		{#if np.now_playing}
			<div class="lyrics-controls">
				<div class="sync-row">
					<span class="sync-label">Lyrics</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div class="scroll-dial"
						onwheel={(e) => { e.preventDefault(); nudgeOffset(e.deltaY > 0 ? 100 : -100); }}
						onpointerdown={(e) => {
							const el = e.currentTarget; el.setPointerCapture(e.pointerId);
							const startX = e.clientX; const startVal = lyricsOffset;
							const move = (me: PointerEvent) => setOffset(Math.round((startVal + (me.clientX - startX) * 20) / 50) * 50);
							const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
							el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
						}}
					>
						<div class="dial-ticks"></div>
						<span class="dial-val" class:adjusted={lyricsOffset !== 0}>{lyricsOffset >= 0 ? '+' : ''}{(lyricsOffset / 1000).toFixed(1)}s</span>
					</div>
					{#if lyricsOffset !== 0}<button class="offset-btn reset" onclick={() => setOffset(0)}>0</button>{/if}
				</div>
				<div class="sync-row">
					<span class="sync-label">Pitch</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div class="scroll-dial"
						onwheel={(e) => { e.preventDefault(); setPitchOffset(pitchOffsetSec + (e.deltaY > 0 ? 0.1 : -0.1)); }}
						onpointerdown={(e) => {
							const el = e.currentTarget; el.setPointerCapture(e.pointerId);
							const startX = e.clientX; const startVal = pitchOffsetSec;
							const move = (me: PointerEvent) => setPitchOffset(Math.round((startVal + (me.clientX - startX) * 0.02) * 20) / 20);
							const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
							el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
						}}
					>
						<div class="dial-ticks"></div>
						<span class="dial-val" class:adjusted={pitchOffsetSec !== 0}>{pitchOffsetSec >= 0 ? '+' : ''}{pitchOffsetSec.toFixed(1)}s</span>
					</div>
					{#if pitchOffsetSec !== 0}<button class="offset-btn reset" onclick={() => setPitchOffset(0)}>0</button>{/if}
				</div>
				<div class="sync-row">
					<span class="sync-label">Gate</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div class="scroll-dial"
						onwheel={(e) => { e.preventDefault(); setPitchNoiseGate(Math.max(0, Math.min(1, pitchNoiseGate + (e.deltaY > 0 ? 0.01 : -0.01)))); }}
						onpointerdown={(e) => {
							const el = e.currentTarget; el.setPointerCapture(e.pointerId);
							const startX = e.clientX; const startVal = pitchNoiseGate;
							const move = (me: PointerEvent) => setPitchNoiseGate(Math.max(0, Math.min(1, startVal + (me.clientX - startX) * 0.002)));
							const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
							el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
						}}
					>
						<div class="dial-ticks"></div>
						<span class="dial-val" class:adjusted={pitchNoiseGate !== 0.05}>{(pitchNoiseGate * 100).toFixed(0)}%</span>
					</div>
					{#if pitchNoiseGate !== 0.05}<button class="offset-btn reset" onclick={() => setPitchNoiseGate(0.05)}>5%</button>{/if}
				</div>
				<button class="search-lyrics-btn" onclick={() => { showLyricsSearch = !showLyricsSearch; if (!searchTitle) searchTitle = np.now_playing ?? ''; }}>
					Search Different Lyrics
				</button>
			</div>
		{/if}

		<!-- Lyrics search panel -->
		{#if showLyricsSearch}
			<div class="lyrics-search-panel glass-light">
				<div class="flex gap-2">
					<input type="text" bind:value={searchTitle} placeholder="Song title" class="lyrics-input" style="flex:2" />
					<input type="text" bind:value={searchArtist} placeholder="Artist" class="lyrics-input" style="flex:1" />
				</div>
				<div class="flex gap-2">
					<button class="search-go-btn" onclick={doLyricsSearch} disabled={searchLoading}>
						{searchLoading ? 'Searching...' : 'Search'}
					</button>
					<button class="search-cancel-btn" onclick={() => { showLyricsSearch = false; candidates = []; }}>Cancel</button>
				</div>
				{#if candidates.length > 0}
					<ul class="candidate-list">
						{#each candidates as c (c.id)}
							<li>
								<button
									class="candidate-btn"
									class:selecting={selectingId === c.id}
									onclick={() => pickCandidate(c.id)}
									disabled={!!selectingId}
								>
									<span class="c-title">{c.title}</span>
									<span class="c-meta">{c.artist} · {c.source}</span>
								</button>
							</li>
						{/each}
					</ul>
				{:else if !searchLoading && searchTitle}
					<p class="text-xs" style="color: var(--color-faint); text-align: center">Search to find lyrics</p>
				{/if}
			</div>
		{/if}

		<!-- Seek bar -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="seek-track"
			onmousedown={seekStart}
			onmousemove={seekMove}
			onmouseup={seekEnd}
			onmouseleave={seekEnd}
			ontouchstart={seekStart}
			ontouchmove={seekMove}
			ontouchend={seekEnd}
		>
			<div class="seek-fill" style="width: {progressPct}%">
				<div class="seek-thumb"></div>
			</div>
		</div>
		<div class="seek-times">
			<span>{formatTime(currentTimeMs / 1000)}</span>
			<span>-{formatTime((np.now_playing_duration ?? 0) - currentTimeMs / 1000)}</span>
		</div>

		<!-- Transport controls -->
		<div class="transport">
			<button class="transport-btn" onclick={doRestart}>
				<i class="fa-solid fa-backward-step"></i>
			</button>
			<button class="transport-btn transport-main" onclick={doPause}>
				{#if np.is_paused}
					<i class="fa-solid fa-play"></i>
				{:else}
					<i class="fa-solid fa-pause"></i>
				{/if}
			</button>
			<button class="transport-btn" onclick={doSkip}>
				<i class="fa-solid fa-forward-step"></i>
			</button>
		</div>

		<!-- Volume -->
		<div class="vol-row">
			<i class="ti ti-volume"></i>
			<input type="range" min="0" max="1" step="0.025" bind:value={volume} onchange={setVolume} class="vol-slider" />
			<i class="ti ti-volume-2"></i>
		</div>

		<!-- Key + Stems -->
		<div class="extras">
			{#if np.now_playing_transpose !== 0}
				<span class="key-badge">Key: {np.now_playing_transpose > 0 ? '+' : ''}{np.now_playing_transpose}</span>
			{/if}
			<div class="key-row">
				<span class="key-label">KEY</span>
				<button class="key-btn" onclick={() => transpose = Math.max(-12, transpose - 1)}>-</button>
				<span class="key-val">{transpose > 0 ? '+' : ''}{transpose}</span>
				<button class="key-btn" onclick={() => transpose = Math.min(12, transpose + 1)}>+</button>
				{#if transpose !== 0}
					<button class="key-apply" onclick={applyTranspose}><i class="ti ti-check"></i></button>
				{/if}
			</div>
			<StemMixer onToggle={toggleStem} />
		</div>

	{:else}
		<!-- Idle state -->
		<div class="idle">
			<div class="idle-icon"><i class="ti ti-music" style="font-size: 3rem; color: var(--color-faint)"></i></div>
			<div class="idle-text">Nothing playing</div>
			<div class="idle-links">
				<a href="{base}/search" class="idle-link">Search Songs</a>
				<a href="{base}/queue" class="idle-link secondary">View Queue</a>
			</div>
		</div>
	{/if}

	<TabBar />
</div>

<style>
	.remote-root {
		position: fixed;
		inset: 0;
		z-index: 1;
		padding: 48px 32px 72px;
		max-width: 430px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 0;
		overflow: hidden;
	}

	/* Up next (slim banner) */
	.up-next {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 0;
		margin-bottom: 8px;
	}
	.up-next-label {
		font-family: var(--font-mono);
		font-size: 0.55rem;
		color: var(--color-faint);
		letter-spacing: 0.1em;
	}
	.up-next-title {
		font-size: 0.75rem;
		color: var(--color-amber);
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		flex: 1;
	}
	.up-next-singer {
		font-size: 0.65rem;
		color: var(--color-faint);
		white-space: nowrap;
	}

	/* Lyrics hero */
	.lyrics-hero {
		flex: 1;
		min-height: 0;
		max-height: 35vh;
		overflow: hidden;
		-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 15%, black 80%, transparent 100%);
		mask-image: linear-gradient(to bottom, transparent 0%, black 15%, black 80%, transparent 100%);
	}

	/* Song info */
	.song-info {
		padding: 0 4px;
		margin-top: 14px;
	}
	.song-title {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 1.2rem;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.song-meta {
		display: flex;
		align-items: center;
		gap: 0;
		margin-top: 2px;
	}
	.song-artist {
		font-size: 0.9rem;
		color: var(--color-teal);
	}
	.meta-dot {
		width: 3px;
		height: 3px;
		border-radius: 50%;
		background: var(--color-faint);
		margin: 0 8px;
		flex-shrink: 0;
	}
	.lyrics-source {
		font-family: var(--font-mono);
		font-size: 0.65rem;
		color: var(--color-faint);
		letter-spacing: 0.03em;
	}

	/* Lyrics controls */
	.lyrics-controls {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin: 6px 0;
	}
	.sync-row {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.sync-label {
		font-size: 0.55rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-faint);
		min-width: 36px;
	}
	.scroll-dial {
		flex: 1;
		height: 28px;
		border-radius: 6px;
		border: 1px solid rgba(255, 255, 255, 0.1);
		background: rgba(0, 0, 0, 0.3);
		overflow: hidden;
		cursor: ew-resize;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		touch-action: none;
		user-select: none;
	}
	.dial-ticks {
		position: absolute;
		inset: 0;
		background: repeating-linear-gradient(
			90deg,
			rgba(255, 255, 255, 0.04) 0px,
			rgba(255, 255, 255, 0.04) 1px,
			transparent 1px,
			transparent 8px
		);
	}
	.dial-val {
		position: relative;
		font-size: 0.65rem;
		font-family: var(--font-mono);
		font-weight: 600;
		color: var(--color-faint);
		pointer-events: none;
	}
	.dial-val.adjusted { color: var(--color-teal); }
	.offset-btn {
		padding: 3px 8px;
		border-radius: 6px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		background: rgba(255, 255, 255, 0.04);
		color: var(--color-dim);
		font-size: 0.6rem;
		font-weight: 600;
		cursor: pointer;
	}
	.offset-btn:active { background: rgba(255, 255, 255, 0.1); }
	.offset-btn.reset { color: var(--color-pink); border-color: rgba(236, 72, 153, 0.2); }
	.search-lyrics-btn {
		padding: 4px 12px;
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		background: rgba(255, 255, 255, 0.04);
		color: var(--color-dim);
		font-size: 0.65rem;
		font-weight: 600;
		cursor: pointer;
	}
	.search-lyrics-btn:active { background: rgba(255, 255, 255, 0.1); }
	.lyrics-search-panel {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 10px;
		border-radius: 10px;
		margin: 4px 0;
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		background: rgba(13, 6, 24, 0.4);
		border: 1px solid rgba(124, 58, 237, 0.15);
	}
	.lyrics-input {
		padding: 6px 10px;
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.1);
		background: rgba(0, 0, 0, 0.3);
		color: var(--color-text);
		font-size: 0.8rem;
		outline: none;
	}
	.lyrics-input:focus { border-color: rgba(124, 58, 237, 0.4); }
	.search-go-btn {
		flex: 1;
		padding: 6px;
		border-radius: 8px;
		border: none;
		background: rgba(124, 58, 237, 0.3);
		color: var(--color-text);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}
	.search-cancel-btn {
		padding: 6px 12px;
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.1);
		background: transparent;
		color: var(--color-dim);
		font-size: 0.75rem;
		cursor: pointer;
	}
	.candidate-list {
		list-style: none;
		padding: 0;
		margin: 4px 0 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
		max-height: 200px;
		overflow-y: auto;
	}
	.candidate-btn {
		width: 100%;
		padding: 8px 10px;
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		background: rgba(255, 255, 255, 0.04);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		text-align: left;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 2px;
		color: inherit;
	}
	.candidate-btn:active, .candidate-btn.selecting {
		background: rgba(124, 58, 237, 0.2);
		border-color: rgba(124, 58, 237, 0.4);
	}
	.c-title {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.c-meta {
		font-size: 0.6rem;
		color: var(--color-faint);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	/* Seek bar */
	.seek-track {
		height: 6px;
		background: rgba(255, 255, 255, 0.12);
		border-radius: 3px;
		position: relative;
		cursor: pointer;
		touch-action: none;
		margin-top: 14px;
	}
	.seek-track:hover { height: 8px; }
	.seek-fill {
		height: 100%;
		background: var(--color-text);
		border-radius: 3px;
		position: relative;
		max-width: 100%;
	}
	.seek-thumb {
		position: absolute;
		right: -6px;
		top: 50%;
		transform: translateY(-50%);
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: var(--color-text);
		opacity: 0;
		transition: opacity 0.15s;
	}
	.seek-track:hover .seek-thumb,
	.seek-track:active .seek-thumb {
		opacity: 1;
	}
	.seek-times {
		display: flex;
		justify-content: space-between;
		font-family: var(--font-mono);
		font-size: 0.65rem;
		color: var(--color-faint);
		margin-top: 4px;
		padding: 0 2px;
	}

	/* Transport */
	.transport {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 32px;
		margin-top: 12px;
	}
	.transport-btn {
		background: none;
		border: none;
		color: var(--color-text);
		font-size: 2rem;
		cursor: pointer;
		padding: 8px;
		line-height: 1;
		-webkit-tap-highlight-color: transparent;
	}
	.transport-btn:active { opacity: 0.5; }
	.transport-main {
		font-size: 3rem;
	}

	/* Volume */
	.vol-row {
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--color-faint);
		font-size: 0.85rem;
		margin-top: 16px;
	}
	.vol-slider {
		flex: 1;
		accent-color: var(--color-text);
		height: 4px;
	}

	/* Extras */
	.extras {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		margin-top: 14px;
	}
	.key-badge {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 6px;
		background: rgba(34, 197, 94, 0.15);
		color: var(--color-green);
		align-self: flex-start;
	}
	.key-row {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
	}
	.key-label { font-family: var(--font-mono); font-size: 0.65rem; color: var(--color-faint); letter-spacing: 0.1em; }
	.key-btn { width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--color-border2); background: var(--color-surface); color: var(--color-text); font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; }
	.key-val { font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600; color: var(--color-text); min-width: 30px; text-align: center; }
	.key-apply { width: 28px; height: 28px; border-radius: 6px; border: none; background: rgba(34, 197, 94, 0.2); color: var(--color-green); cursor: pointer; display: flex; align-items: center; justify-content: center; }

	/* Idle */
	.idle {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 12px;
		padding: 40px 0;
	}
	.idle-icon { opacity: 0.4; }
	.idle-text { font-size: 1.1rem; color: var(--color-faint); font-weight: 500; }
	.idle-links { display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 260px; margin-top: 8px; }
	.idle-link {
		display: block;
		text-align: center;
		padding: 12px;
		border-radius: 12px;
		font-weight: 600;
		text-decoration: none;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-teal);
	}
	.idle-link.secondary { color: var(--color-dim); }
</style>
