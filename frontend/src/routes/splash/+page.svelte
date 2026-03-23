<script lang="ts">
	/**
	 * Splash screen (TV Display) — full-screen karaoke player.
	 * Video + pitch graph + lyrics overlay + now-playing bar + queue preview.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { getState, fetchNowPlaying, type NowPlaying } from '$lib/stores/playback.svelte';
	import { loadLyrics, clearLyrics } from '$lib/stores/lyrics.svelte';
	import { emit, on } from '$lib/stores/socket.svelte';
	import { start as startPitch, stop as stopPitch, type PitchReading } from '$lib/audio/pitch-detector';
	import * as stemMixer from '$lib/audio/stem-mixer';
	import LyricsOverlay from '$components/LyricsOverlay.svelte';
	import PitchGraph from '$components/PitchGraph.svelte';
	import Hls from 'hls.js';

	const np: NowPlaying = $derived(getState());

	let video: HTMLVideoElement;
	let currentTimeMs = $state(0);
	let currentTimeSec = $state(0);
	let singerPitch: PitchReading | null = $state(null);
	let pitchData: Array<{ t: number; hz: number; midi: number }> = $state([]);
	let hlsInstance: Hls | null = null;
	let currentVideoUrl: string | null = null;
	let isMaster = $state(false);
	let showPitchGraph = $state(true);

	// Format time for display
	function formatTime(seconds: number): string {
		if (isNaN(seconds)) return '00:00';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	// rAF loop for lyrics sync + pitch sync
	let rafId: number | null = null;
	function frameLoop() {
		if (video && !video.paused) {
			currentTimeMs = video.currentTime * 1000;
			currentTimeSec = video.currentTime;
		}
		rafId = requestAnimationFrame(frameLoop);
	}

	// Load video when now_playing_url changes
	$effect(() => {
		const url = np.now_playing_url;
		if (!url || url === currentVideoUrl || !video) return;

		currentVideoUrl = url;
		const fullUrl = `${base}${url}`;

		// Clean up previous
		if (hlsInstance) {
			hlsInstance.destroy();
			hlsInstance = null;
		}

		if (url.endsWith('.m3u8')) {
			if (Hls.isSupported()) {
				hlsInstance = new Hls({ startPosition: 0 });
				hlsInstance.loadSource(fullUrl);
				hlsInstance.attachMedia(video);
			} else if (video.canPlayType('application/vnd.apple.mpegurl')) {
				video.src = fullUrl;
				video.load();
			}
		} else {
			video.src = fullUrl;
			video.load();
		}

		video.volume = np.volume;
		video.play().catch((e) => console.error('Play failed:', e));

		// Load lyrics for this song
		const streamUid = url.split('/').pop()?.replace(/\.(m3u8|mp4)$/, '') ?? '';
		loadLyrics(streamUid);

		// Load pitch data
		fetch(`${base}/api/pitch/${streamUid}`)
			.then((r) => (r.ok ? r.json() : []))
			.then((data) => (pitchData = data))
			.catch(() => (pitchData = []));

		// Setup stems if available
		if (np.stems_available && np.stem_urls) {
			stemMixer.init();
			stemMixer.loadStems(np.stem_urls).then((ok) => {
				if (ok && video && !video.paused) {
					video.volume = 0; // Mute video, stems handle audio
					stemMixer.play(video.currentTime);
					stemMixer.applyMix(np.stem_mix, np.volume);
				}
			});
		}
	});

	// Handle song ending
	$effect(() => {
		if (!np.now_playing && currentVideoUrl) {
			currentVideoUrl = null;
			if (hlsInstance) {
				hlsInstance.destroy();
				hlsInstance = null;
			}
			stemMixer.teardown();
			clearLyrics();
			pitchData = [];
		}
	});

	// Sync stem mix changes
	$effect(() => {
		if (stemMixer.isActive()) {
			stemMixer.applyMix(np.stem_mix, np.volume);
		}
	});

	// Socket event handlers
	let unsubs: Array<() => void> = [];

	onMount(() => {
		// Register as splash screen
		emit('register_splash');

		unsubs = [
			on('splash_role', (role: any) => {
				isMaster = role === 'master';
			}),
			on('pause', () => {
				video?.pause();
				stemMixer.pause();
			}),
			on('play', () => {
				video?.play();
				stemMixer.resume();
			}),
			on('skip', () => {
				video?.pause();
				stemMixer.teardown();
			}),
			on('restart', () => {
				if (video) {
					video.currentTime = 0;
					video.play();
				}
				stemMixer.play(0);
			}),
			on('volume', (val: any) => {
				let newVol: number;
				if (val === 'up') newVol = Math.min(1, np.volume + 0.1);
				else if (val === 'down') newVol = Math.max(0, np.volume - 0.1);
				else newVol = val;

				if (!stemMixer.isActive() && video) {
					video.volume = newVol;
				}
				stemMixer.setMasterVolume(newVol);
			}),
		];

		// Start rAF loop
		frameLoop();

		// Report playback position to server (master only)
		const posInterval = setInterval(() => {
			if (isMaster && video && !video.paused) {
				emit('playback_position', video.currentTime);
			}
		}, 1000);

		// Stem sync interval
		const stemInterval = setInterval(() => {
			if (stemMixer.isActive() && video && !video.paused) {
				stemMixer.syncToVideo(video.currentTime);
			}
		}, 500);

		// Start pitch detection
		startPitch((reading) => {
			singerPitch = reading;
		});

		// Initial state
		fetchNowPlaying();

		return () => {
			clearInterval(posInterval);
			clearInterval(stemInterval);
		};
	});

	onDestroy(() => {
		if (rafId) cancelAnimationFrame(rafId);
		unsubs.forEach((fn) => fn());
		stopPitch();
		stemMixer.teardown();
		if (hlsInstance) hlsInstance.destroy();
	});

	// Video event handlers
	function onVideoEnded() {
		if (isMaster) {
			emit('end_song', 'complete');
		}
	}

	function onVideoPlay() {
		emit('start_song');
	}
</script>

<svelte:head>
	<title>HomeKaraoke — TV</title>
</svelte:head>

<div class="splash-root">
	<!-- Background video (ambient, behind everything) -->
	<div class="bg-layer">
		{#if !np.now_playing}
			<video
				class="bg-video"
				src="{base}/stream/bg_video"
				muted
				loop
				autoplay
				playsinline
			></video>
		{/if}
	</div>

	<!-- Main video player -->
	<div class="video-layer" class:visible={!!np.now_playing}>
		<video
			bind:this={video}
			class="main-video"
			playsinline
			disableremoteplayback
			on:ended={onVideoEnded}
			on:play={onVideoPlay}
		></video>
	</div>

	<!-- Pitch graph overlay (top) -->
	<PitchGraph
		referenceNotes={pitchData}
		{singerPitch}
		{currentTimeSec}
		visible={showPitchGraph && !!np.now_playing && pitchData.length > 0}
	/>

	<!-- Lyrics overlay (bottom) -->
	<LyricsOverlay {currentTimeMs} />

	<!-- Now playing bar (bottom) -->
	{#if np.now_playing}
		<div class="now-playing-bar">
			<div class="np-info">
				<span class="np-user">🎤 {np.now_playing_user ?? ''}</span>
				<span class="np-divider">•</span>
				<span class="np-title">{np.now_playing}</span>
				{#if np.now_playing_transpose !== 0}
					<span class="np-key">Key: {np.now_playing_transpose > 0 ? '+' : ''}{np.now_playing_transpose}</span>
				{/if}
			</div>
			<div class="np-progress">
				<div class="np-progress-bar">
					<div
						class="np-progress-fill"
						style="width: {np.now_playing_duration ? (currentTimeSec / np.now_playing_duration) * 100 : 0}%"
					></div>
				</div>
				<span class="np-time">
					{formatTime(currentTimeSec)} / {formatTime(np.now_playing_duration ?? 0)}
				</span>
			</div>
		</div>
	{/if}

	<!-- Up next (bottom-right) -->
	{#if np.up_next}
		<div class="up-next">
			<span class="up-next-label">UP NEXT</span>
			<span class="up-next-song">{np.up_next}</span>
			<span class="up-next-singer">🎤 {np.next_user ?? ''}</span>
		</div>
	{/if}

	<!-- Logo (when idle) -->
	{#if !np.now_playing}
		<div class="logo-container">
			<h1 class="gradient-text logo-text">HomeKaraoke</h1>
		</div>
	{/if}
</div>

<style>
	.splash-root {
		position: fixed;
		inset: 0;
		background: #000;
		overflow: hidden;
	}

	.bg-layer {
		position: absolute;
		inset: 0;
		z-index: 0;
	}
	.bg-video {
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0.6;
	}

	.video-layer {
		position: absolute;
		inset: 0;
		z-index: 1;
		display: none;
	}
	.video-layer.visible {
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.main-video {
		width: 100%;
		height: 100%;
		object-fit: contain;
	}

	.logo-container {
		position: absolute;
		inset: 0;
		z-index: 2;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.logo-text {
		font-family: var(--font-display);
		font-size: 5rem;
		font-weight: 800;
	}

	/* Now playing bar */
	.now-playing-bar {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 6;
		padding: 8px 20px 12px;
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.85));
	}
	.np-info {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.95rem;
		color: var(--color-text);
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
	}
	.np-user {
		color: var(--color-teal);
		font-weight: 600;
	}
	.np-divider {
		color: var(--color-faint);
	}
	.np-title {
		font-weight: 500;
	}
	.np-key {
		color: var(--color-green);
		font-size: 0.8rem;
		font-family: var(--font-mono);
	}
	.np-progress {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 4px;
	}
	.np-progress-bar {
		flex: 1;
		height: 3px;
		background: rgba(255, 255, 255, 0.15);
		border-radius: 2px;
		overflow: hidden;
	}
	.np-progress-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--color-purple), var(--color-teal));
		border-radius: 2px;
		transition: width 0.3s linear;
	}
	.np-time {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--color-dim);
		min-width: 90px;
		text-align: right;
	}

	/* Up next */
	.up-next {
		position: absolute;
		bottom: 60px;
		right: 20px;
		z-index: 6;
		text-align: right;
		text-shadow: 0 1px 4px rgba(0, 0, 0, 0.9);
	}
	.up-next-label {
		display: block;
		font-family: var(--font-mono);
		font-size: 0.65rem;
		color: var(--color-faint);
		letter-spacing: 0.15em;
		text-transform: uppercase;
	}
	.up-next-song {
		display: block;
		font-size: 1rem;
		color: var(--color-amber);
		font-weight: 600;
	}
	.up-next-singer {
		font-size: 0.85rem;
		color: var(--color-green);
	}
</style>
