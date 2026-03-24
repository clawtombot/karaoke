<script lang="ts">
	/**
	 * Splash screen (TV Display) — full-screen karaoke player.
	 * Video + pitch graph + lyrics overlay + now-playing bar + queue preview.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { getState, fetchNowPlaying, type NowPlaying } from '$lib/stores/playback.svelte';
	import { loadLyrics, clearLyrics, reloadLyrics, applyRemoteOffset } from '$lib/stores/lyrics.svelte';
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
	let backingPitchData: Array<{ t: number; hz: number; midi: number }> = $state([]);
	let singerInfo: { lead?: string; backing?: string } = $state({});
	let pitchLoading = $state(false);
	let pitchRetryId: ReturnType<typeof setInterval> | null = null;
	let hlsInstance: Hls | null = null;
	let currentVideoUrl: string | null = null;
	let isMaster = $state(false);
	let showPitchGraph = $state(true);
	let pitchOffsetSec = $state(0);
	let pitchNoiseGate = $state(0.05);
	let stemsReady = false; // Stems loaded but waiting for video to play
	let stemsInitiated = false; // Stem loading started for current song
	let stemGeneration = 0; // Increments on song change to cancel stale loads

	function toggleStem(stem: string) {
		emit('stem_toggle', stem);
	}

	// Format time for display
	function formatTime(seconds: number): string {
		if (isNaN(seconds)) return '00:00';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	// Try to play video, with muted fallback for autoplay policy
	function tryPlay() {
		if (!video) return;
		video.play().then(() => {
			// Unmuted autoplay succeeded — resume AudioContext in same context
			// so stems can take over without user gesture
			stemMixer.init();
		}).catch(() => {
			// Autoplay blocked — try muted (browsers allow muted autoplay)
			console.warn('[splash] autoplay blocked, retrying muted');
			video.muted = true;
			video.play().catch((e) => console.error('[splash] play failed even muted:', e));
		});
	}

	// Start stems when video actually begins playing
	function activateStems() {
		if (!stemsReady || !video || video.paused || !stemsInitiated) return;
		const gen = stemGeneration; // Capture to guard async callbacks
		stemMixer.play(video.currentTime);
		stemMixer.applyMix(np.stem_mix, np.volume);

		// Mute video as soon as AudioContext is ready (immediate or deferred).
		// This prevents dual audio — stems + video playing simultaneously.
		stemMixer.onReady(() => {
			if (gen !== stemGeneration) return; // Stale — song changed
			if (video) {
				video.volume = 0;
				video.muted = false;
			}
		});

		if (!stemMixer.isReady()) {
			// AudioContext suspended (no user gesture yet) — keep video audible
			// until stems activate via onReady callback above
			video.muted = false;
			video.volume = np.volume;
		}
		stemsReady = false;
	}

	// Load stems from current state and activate when ready
	function loadAndActivateStems() {
		if (!np.stem_urls || stemsInitiated) return;
		stemsInitiated = true;
		const gen = stemGeneration; // Capture current generation
		stemMixer.init();
		const prefixedUrls = Object.fromEntries(
			Object.entries(np.stem_urls).map(([k, v]) => [k, `${base}${v}`])
		);
		stemMixer.loadStems(prefixedUrls).then((ok) => {
			// Ignore if a new song started while we were loading
			if (gen !== stemGeneration) return;
			if (ok) {
				stemsReady = true;
				activateStems();
			}
		});
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
		stemsReady = false;
		stemsInitiated = false;
		stemGeneration++; // Invalidate any in-flight stem loads from previous song
		const fullUrl = `${base}${url}`;

		// Clean up previous song completely — stop stems BEFORE loading new video
		// to prevent old stems playing alongside new video audio
		stemMixer.teardown();
		if (video) video.pause();
		if (hlsInstance) {
			hlsInstance.destroy();
			hlsInstance = null;
		}

		// Resume at current server position if mid-song (refresh or new splash)
		const resumePos = np.now_playing_position ?? 0;

		if (url.endsWith('.m3u8')) {
			if (Hls.isSupported()) {
				const hls = new Hls({
					startPosition: resumePos,
					maxBufferLength: 30,
					maxMaxBufferLength: 60,
				});
				hlsInstance = hls;

				// Wait for manifest before playing (prevents race condition)
				hls.on(Hls.Events.MANIFEST_PARSED, () => {
					video.volume = np.volume;
					tryPlay();
				});

				// Error recovery
				hls.on(Hls.Events.ERROR, (_event, data) => {
					if (!data.fatal) return;
					console.error('[hls] fatal error:', data.type, data.details);
					if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
						console.warn('[hls] network error, retrying...');
						hls.startLoad();
					} else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
						console.warn('[hls] media error, recovering...');
						hls.recoverMediaError();
					} else {
						// Unrecoverable — destroy and reload after delay
						console.error('[hls] unrecoverable, reloading in 2s...');
						hls.destroy();
						hlsInstance = null;
						setTimeout(() => {
							if (currentVideoUrl === url) {
								currentVideoUrl = null; // Allow re-trigger of $effect
							}
						}, 2000);
					}
				});

				hls.loadSource(fullUrl);
				hls.attachMedia(video);
			} else if (video.canPlayType('application/vnd.apple.mpegurl')) {
				// Safari native HLS
				video.src = fullUrl;
				video.load();
				video.volume = np.volume;
				tryPlay();
			}
		} else {
			video.src = fullUrl;
			video.load();
			video.volume = np.volume;
			if (resumePos > 0) {
				video.addEventListener('loadedmetadata', () => { video.currentTime = resumePos; }, { once: true });
			}
			tryPlay();
		}

		// Load lyrics for this song
		const streamUid = url.split('/').pop()?.replace(/\.(m3u8|mp4)$/, '') ?? '';
		loadLyrics(streamUid);

		// Load pitch data (retry until available — stems may still be splitting)
		if (pitchRetryId) clearInterval(pitchRetryId);
		pitchData = [];
		backingPitchData = [];
		singerInfo = {};
		pitchLoading = true;
		const fetchPitch = () => {
			fetch(`${base}/api/pitch/${streamUid}`)
				.then((r) => (r.ok ? r.json() : null))
				.then((data) => {
					if (data && data.length > 0) {
						pitchData = data;
						pitchLoading = false;
						if (pitchRetryId) { clearInterval(pitchRetryId); pitchRetryId = null; }
					}
				})
				.catch(() => {});
			// Backing vocals pitch (harmony line)
			fetch(`${base}/api/pitch_backing/${streamUid}`)
				.then((r) => (r.ok ? r.json() : null))
				.then((data) => { if (data && data.length > 0) backingPitchData = data; })
				.catch(() => {});
			// Singer gender info (for colors)
			fetch(`${base}/api/singer/${streamUid}`)
				.then((r) => (r.ok ? r.json() : null))
				.then((data) => { if (data) singerInfo = data; })
				.catch(() => {});
		};
		fetchPitch();
		pitchRetryId = setInterval(fetchPitch, 5000);

		// Load stems if already available (cached from previous play)
		if (np.stems_available && np.stem_urls) {
			loadAndActivateStems();
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
			backingPitchData = [];
			singerInfo = {};
			pitchLoading = false;
			if (pitchRetryId) { clearInterval(pitchRetryId); pitchRetryId = null; }
		}
	});

	// Sole play/pause controller — driven by server state (np.is_paused).
	// No direct pause/play socket handlers — this $effect is the single
	// source of truth, preventing race conditions from dual controllers.
	$effect(() => {
		const paused = np.is_paused;
		if (!video || !np.now_playing || !currentVideoUrl) return;
		if (paused && !video.paused) {
			video.pause();
			stemMixer.pause();
		} else if (!paused && video.paused) {
			video.play().catch(() => {
				// Autoplay blocked — will play on next user gesture (onUserGesture)
			});
			if (stemMixer.isActive()) stemMixer.resume();
		}
	});

	// Sync stem mix changes — read reactive deps BEFORE the non-reactive
	// isActive() gate so Svelte always subscribes to stem_mix/volume changes.
	$effect(() => {
		const mix = np.stem_mix;
		const vol = np.volume;
		if (stemMixer.isActive()) {
			stemMixer.applyMix(mix, vol);
		}
	});

	// Socket event handlers
	let unsubs: Array<() => void> = [];

	onMount(() => {
		// Pre-create AudioContext early — may start 'running' if browser
		// allows autoplay (high Media Engagement Index or user gesture carried over)
		stemMixer.init();

		// Register as splash screen (only here — the 'connect' handler below
		// handles RE-connections, not the initial connect which already happened
		// via +layout.svelte before this onMount runs)
		emit('register_splash');

		unsubs = [
			on('splash_role', (role: any) => {
				isMaster = role === 'master';
			}),
			on('playback_position', (position: any) => {
				// Slave sync: master broadcasts position, slaves align to it
				if (!isMaster && video && !video.paused) {
					const drift = Math.abs(video.currentTime - position);
					if (drift > 0.5) {
						video.currentTime = position;
						if (stemMixer.isActive()) {
							stemMixer.syncToVideo(position);
						}
					}
				}
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
			on('seek', (pos: any) => {
				if (video) {
					video.currentTime = pos;
					if (stemMixer.isActive()) {
						stemMixer.syncToVideo(pos);
					}
				}
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
			// Re-register and re-fetch after socket reconnects
			on('connect', () => {
				console.log('[splash] socket reconnected, re-registering');
				emit('register_splash');
				fetchNowPlaying();
			}),
			on('lyrics_reload', () => {
				console.log('[splash] lyrics reload requested');
				reloadLyrics();
			}),
			on('lyrics_offset', (ms: any) => {
				applyRemoteOffset(Number(ms));
			}),
			on('pitch_offset', (sec: any) => {
				pitchOffsetSec = Number(sec);
			}),
			on('pitch_noise_gate', (gate: any) => {
				pitchNoiseGate = Number(gate);
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

		// Poll for stem availability while DNN is splitting
		const stemPollInterval = setInterval(() => {
			if (
				np.vocal_splitter_enabled &&
				!np.stems_available &&
				np.now_playing_url &&
				!np.stem_progress?.error
			) {
				fetchNowPlaying();
			}
			// Hot-swap: stems became available mid-playback
			if (np.stems_available && np.stem_urls && currentVideoUrl && !stemsInitiated) {
				console.log('[splash] stems now available mid-playback, hot-swapping');
				loadAndActivateStems();
			}
		}, 5000);

		// Start pitch detection
		startPitch((reading) => {
			singerPitch = reading;
		});

		// Initial state
		fetchNowPlaying();

		return () => {
			clearInterval(posInterval);
			clearInterval(stemInterval);
			clearInterval(stemPollInterval);
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
		// Always stop stems on video end — prevents leftover audio if next song loads
		stemMixer.teardown();
		if (isMaster) {
			emit('end_song', 'complete');
		}
	}

	function onVideoPlay() {
		if (isMaster) emit('start_song');
		// Stems may have loaded while video was buffering — activate now
		activateStems();
	}

	/** Resume AudioContext on first user gesture and swap audio to stems. */
	function onUserGesture() {
		// Unmute video if it was muted by autoplay fallback
		if (video && video.muted) {
			video.muted = false;
			video.volume = np.volume;
		}

		// Resume suspended AudioContext with user gesture context.
		// init() now calls ctx.resume() even if already initialized.
		stemMixer.init();

		// If stems are active and AudioContext just became ready, swap to stem audio
		if (stemsInitiated && stemMixer.isActive() && stemMixer.isReady() && video) {
			video.volume = 0;
			stemMixer.syncToVideo(video.currentTime);
		}

		// If video is paused but should be playing, try to play
		if (video && video.paused && !np.is_paused && currentVideoUrl) {
			video.play().catch(() => {});
		}
	}

	async function seekFromClick(e: MouseEvent) {
		e.stopPropagation(); // Don't trigger onUserGesture
		if (!np.now_playing_duration || !video) return;
		const bar = e.currentTarget as HTMLElement;
		const rect = bar.getBoundingClientRect();
		const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
		const pos = ratio * np.now_playing_duration;
		video.currentTime = pos;
		if (stemMixer.isActive()) {
			stemMixer.syncToVideo(pos);
		}
		// Resume playback if paused (seek implies intent to play)
		if (video.paused) {
			video.play().catch(() => {});
		}
		await fetch(`${base}/seek/${pos}`);
	}
</script>

<svelte:head>
	<title>HomeKaraoke — TV</title>
</svelte:head>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="splash-root" onclick={onUserGesture}>
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
			onended={onVideoEnded}
			onplay={onVideoPlay}
		></video>
	</div>

	<!-- Pitch graph overlay (top) -->
	<PitchGraph
		referenceNotes={pitchData}
		backingNotes={backingPitchData}
		{singerPitch}
		{currentTimeSec}
		visible={showPitchGraph && !!np.now_playing}
		loading={pitchLoading && pitchData.length === 0}
		offsetSec={pitchOffsetSec}
		noiseGate={pitchNoiseGate}
		leadColor={singerInfo.lead === 'female' ? '#ff69b4' : '#4da6ff'}
		backingColor={singerInfo.backing === 'female' ? '#ff69b4' : '#4da6ff'}
	/>

	<!-- Lyrics overlay (bottom) -->
	<LyricsOverlay {currentTimeMs} />

	<!-- Stem indicators (right side, vertical) -->
	{#if np.now_playing && np.stems_available}
		<div class="splash-stems">
			{#each Object.keys(np.stem_urls ?? {}).map(name => {
				const icons: Record<string, string> = {
					lead_vocals: 'fa-solid fa-microphone',
					backing_vocals: 'fa-solid fa-users',
					vocals: 'fa-solid fa-microphone',
					drums: 'fa-solid fa-drum',
					bass: 'ti ti-wave-sine',
					guitar: 'fa-solid fa-guitar',
					piano: 'ti ti-piano',
					other: 'ti ti-music',
				};
				return { name, icon: icons[name] ?? 'ti ti-music' };
			}) as stem}
				<button
					class="stem-ind"
					class:on={np.stem_mix[stem.name] ?? true}
					onclick={() => toggleStem(stem.name)}
					title={stem.name}
				>
					<i class={stem.icon}></i>
				</button>
			{/each}
		</div>
	{/if}

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
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
				<div class="np-progress-bar seekable" onclick={(e) => seekFromClick(e)}>
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

	/* Stem indicators (right side vertical) */
	.splash-stems {
		position: absolute;
		right: 12px;
		top: 50%;
		transform: translateY(-50%);
		z-index: 6;
		display: flex;
		flex-direction: column;
		gap: 6px;
		opacity: 0.5;
		transition: opacity 0.2s;
	}
	.splash-stems:hover {
		opacity: 1;
	}
	.stem-ind {
		width: 32px;
		height: 32px;
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		background: rgba(0, 0, 0, 0.4);
		color: rgba(255, 255, 255, 0.2);
		font-size: 0.85rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s;
	}
	.stem-ind.on {
		color: var(--color-teal, #00d2ff);
		border-color: rgba(0, 210, 255, 0.3);
		background: rgba(0, 210, 255, 0.08);
	}
	.stem-ind:hover {
		border-color: rgba(255, 255, 255, 0.3);
		background: rgba(255, 255, 255, 0.1);
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
	.np-progress-bar.seekable {
		cursor: pointer;
		height: 8px;
	}
	.np-progress-bar.seekable:hover {
		height: 10px;
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
