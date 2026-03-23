<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { getState, fetchNowPlaying } from '$lib/stores/playback.svelte';
	import { loadLyrics, clearLyrics } from '$lib/stores/lyrics.svelte';
	import NowPlaying from '$components/NowPlaying.svelte';
	import LyricsPanel from '$components/LyricsPanel.svelte';
	import StemMixer from '$components/StemMixer.svelte';

	const np = $derived(getState());
	let currentTimeMs = $state(0);
	let volume = $state(0.85);
	let transpose = $state(0);
	let positionInterval: ReturnType<typeof setInterval> | null = null;

	$effect(() => { volume = np.volume; });

	let lastUrl: string | null = null;
	$effect(() => {
		const url = np.now_playing_url;
		if (url && url !== lastUrl) {
			lastUrl = url;
			const uid = url.split('/').pop()?.replace(/\.(m3u8|mp4)$/, '') ?? '';
			loadLyrics(uid);
		} else if (!url && lastUrl) {
			lastUrl = null;
			clearLyrics();
		}
	});

	$effect(() => {
		if (np.now_playing_position) currentTimeMs = np.now_playing_position * 1000;
	});

	async function doSkip() { await fetch('/skip'); }
	async function doPause() { await fetch('/pause'); }
	async function doRestart() { if (confirm('Restart?')) await fetch('/restart'); }
	async function setVolume(e: Event) {
		const val = (e.target as HTMLInputElement).value;
		volume = parseFloat(val);
		await fetch('/volume/' + val);
	}
	async function applyTranspose() {
		if (transpose !== 0 && confirm('Transpose ' + (transpose > 0 ? '+' : '') + transpose + '?')) {
			await fetch('/transpose/' + transpose);
			transpose = 0;
		}
	}
	async function toggleStem(stem: string) { await fetch('/stem_toggle/' + stem); }

	onMount(() => {
		fetchNowPlaying();
		positionInterval = setInterval(() => {
			if (np.now_playing_position) currentTimeMs = np.now_playing_position * 1000;
		}, 250);
	});
	onDestroy(() => {
		if (positionInterval) clearInterval(positionInterval);
	});
</script>

<svelte:head><title>Remote — HomeKaraoke</title></svelte:head>

<div class="remote-root">
	<div class="remote-content">
		<NowPlaying />

		{#if np.now_playing}
			<div class="controls">
				<button class="ctrl-btn" on:click={doRestart}><i class="ti ti-player-skip-back"></i></button>
				<button class="ctrl-btn primary" on:click={doPause}>
					<i class="ti" class:ti-player-pause={!np.is_paused} class:ti-player-play={np.is_paused}></i>
				</button>
				<button class="ctrl-btn danger" on:click={doSkip}><i class="ti ti-player-skip-forward"></i></button>
			</div>

			<div class="vol-section">
				<i class="ti ti-volume" style="color: var(--color-dim); font-size: 0.85rem"></i>
				<input type="range" min="0" max="1" step="0.025" bind:value={volume} on:change={setVolume} class="vol-slider" />
				<i class="ti ti-volume-2" style="color: var(--color-dim); font-size: 0.85rem"></i>
			</div>

			<div class="key-section">
				<span class="key-label">KEY</span>
				<button class="key-btn" on:click={() => transpose = Math.max(-12, transpose - 1)}>-</button>
				<span class="key-val">{transpose > 0 ? '+' : ''}{transpose}</span>
				<button class="key-btn" on:click={() => transpose = Math.min(12, transpose + 1)}>+</button>
				{#if transpose !== 0}
					<button class="key-apply" on:click={applyTranspose}><i class="ti ti-check"></i></button>
				{/if}
			</div>

			<div class="mixer-section"><StemMixer onToggle={toggleStem} /></div>
			<div class="lyrics-section"><LyricsPanel {currentTimeMs} /></div>
		{/if}

		{#if np.up_next}
			<div class="glass-light up-next-card">
				<div class="up-next-label">Up Next</div>
				<div class="up-next-title">{np.up_next}</div>
				<div class="up-next-singer"><i class="ti ti-microphone-2"></i> {np.next_user ?? ''}</div>
			</div>
		{/if}

		{#if !np.now_playing}
			<div class="mt-4 flex flex-col gap-3">
				<a href="/search" class="glass-light block rounded-xl px-6 py-3 text-center font-semibold" style="color: var(--color-teal)">Search Songs</a>
				<a href="/queue" class="glass-light block rounded-xl px-6 py-3 text-center font-semibold" style="color: var(--color-dim)">View Queue</a>
			</div>
		{/if}
	</div>

	<nav class="tab-bar">
		<a href="/remote" class="tab active"><i class="ti ti-home-2"></i><span>Home</span></a>
		<a href="/search" class="tab"><i class="ti ti-search"></i><span>Search</span></a>
		<a href="/queue" class="tab"><i class="ti ti-list-numbers"></i><span>Queue</span></a>
		<a href="/splash" class="tab" target="_blank"><i class="ti ti-device-tv"></i><span>TV</span></a>
	</nav>
</div>

<style>
	.remote-root { position: relative; z-index: 1; min-height: 100vh; padding-bottom: 70px; }
	.remote-content { max-width: 430px; margin: 0 auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
	.controls { display: flex; justify-content: center; align-items: center; gap: 16px; }
	.ctrl-btn { width: 44px; height: 44px; border-radius: 50%; border: 1px solid var(--color-border2); background: var(--color-surface); color: var(--color-text); font-size: 1.1rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
	.ctrl-btn:hover { background: var(--color-surface2); }
	.ctrl-btn.primary { width: 52px; height: 52px; background: linear-gradient(135deg, var(--color-purple), var(--color-teal)); border: none; font-size: 1.3rem; box-shadow: 0 0 20px rgba(124, 58, 237, 0.35); }
	.ctrl-btn.danger:hover { border-color: var(--color-pink); color: var(--color-pink); }
	.vol-section { display: flex; align-items: center; gap: 8px; padding: 0 8px; }
	.vol-slider { flex: 1; accent-color: var(--color-teal); }
	.key-section { display: flex; align-items: center; justify-content: center; gap: 8px; }
	.key-label { font-family: var(--font-mono); font-size: 0.65rem; color: var(--color-faint); letter-spacing: 0.1em; }
	.key-btn { width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--color-border2); background: var(--color-surface); color: var(--color-text); font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; }
	.key-val { font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600; color: var(--color-text); min-width: 30px; text-align: center; }
	.key-apply { width: 28px; height: 28px; border-radius: 6px; border: none; background: rgba(34, 197, 94, 0.2); color: var(--color-green); cursor: pointer; display: flex; align-items: center; justify-content: center; }
	.mixer-section { padding: 8px 0; }
	.lyrics-section { min-height: 150px; max-height: 300px; overflow: hidden; border-radius: 12px; }
	.up-next-card { padding: 10px 14px; border-radius: 12px; }
	.up-next-label { font-family: var(--font-mono); font-size: 0.6rem; color: var(--color-faint); letter-spacing: 0.15em; text-transform: uppercase; }
	.up-next-title { font-weight: 600; font-size: 0.9rem; color: var(--color-amber); }
	.up-next-singer { font-size: 0.75rem; color: var(--color-green); }
	.tab-bar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 50; display: flex; justify-content: space-around; padding: 8px 0 env(safe-area-inset-bottom, 8px); background: rgba(8, 4, 18, 0.95); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-top: 1px solid var(--color-border); }
	.tab { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 4px 16px; color: var(--color-faint); text-decoration: none; font-size: 0.6rem; font-weight: 600; }
	.tab i { font-size: 1.2rem; }
	.tab:hover, .tab.active { color: var(--color-teal); }
</style>
