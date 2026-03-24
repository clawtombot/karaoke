<script lang="ts">
	/**
	 * Search page — local library + YouTube search with download/queue.
	 */
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import Cookies from 'js-cookie';
	import TabBar from '$components/TabBar.svelte';

	interface LocalResult {
		path: string;
		fileName: string;
		type: string;
	}

	interface YTResult {
		title: string;
		url: string;
		id: string;
		channel: string | null;
		duration: string | null;
		thumbnail: string;
	}

	let query = $state('');
	let localResults: LocalResult[] = $state([]);
	let ytResults: YTResult[] = $state([]);
	let isSearchingLocal = $state(false);
	let isSearchingYT = $state(false);
	let autoQueue = $state(true);
	let addedSongs = $state(new Set<string>());
	let downloadingUrls = $state(new Set<string>());
	let downloadedUrls = $state(new Set<string>());
	let toastMsg = $state('');
	let toastTimer: ReturnType<typeof setTimeout> | null = null;
	let previewUrl = $state('');
	let previewStreamUrl = $state('');
	let showPreview = $state(false);
	let previewLoading = $state(false);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	function showToast(msg: string) {
		toastMsg = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toastMsg = ''), 2500);
	}

	function onInput() {
		if (debounceTimer) clearTimeout(debounceTimer);
		if (!query.trim()) {
			localResults = [];
			isSearchingLocal = false;
			return;
		}
		isSearchingLocal = true;
		debounceTimer = setTimeout(doLocalSearch, 300);
	}

	async function doLocalSearch() {
		const q = query.trim();
		if (!q) return;
		try {
			const res = await fetch(api(`/autocomplete?q=${encodeURIComponent(q)}`));
			if (res.ok) localResults = await res.json();
		} catch (e) {
			console.error('[search] autocomplete failed:', e);
		} finally {
			isSearchingLocal = false;
		}
	}

	async function doYouTubeSearch() {
		const q = query.trim();
		if (!q) return;
		isSearchingYT = true;
		ytResults = [];
		try {
			const params = new URLSearchParams({
				search_string: q,
			});
			const res = await fetch(api(`/api/youtube/search?${params}`));
			if (res.ok) ytResults = await res.json();
		} catch (e) {
			console.error('[search] youtube search failed:', e);
		} finally {
			isSearchingYT = false;
		}
	}

	function onSearchSubmit(e: Event) {
		e.preventDefault();
		doYouTubeSearch();
	}

	async function addToQueue(path: string, label: string) {
		const user = Cookies.get('user') ?? 'Guest';
		try {
			const res = await fetch(api('/enqueue'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ song: path, user }),
			});
			if (res.ok) {
				addedSongs = new Set([...addedSongs, path]);
				showToast(`Queued: ${label}`);
			}
		} catch (e) {
			showToast('Failed to queue');
		}
	}

	async function downloadSong(url: string, title: string) {
		const user = Cookies.get('user') ?? 'Guest';
		downloadingUrls = new Set([...downloadingUrls, url]);
		try {
			const res = await fetch(api('/download'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					song_url: url,
					song_added_by: user,
					song_title: title,
					queue: autoQueue,
				}),
			});
			if (res.ok) {
				downloadedUrls = new Set([...downloadedUrls, url]);
				showToast(autoQueue ? `Downloading + queuing: ${title}` : `Downloading: ${title}`);
			}
		} catch (e) {
			showToast('Download failed');
		} finally {
			downloadingUrls.delete(url);
			downloadingUrls = new Set(downloadingUrls);
		}
	}

	async function openPreview(url: string) {
		previewUrl = url;
		showPreview = true;
		previewLoading = true;
		previewStreamUrl = '';
		try {
			const res = await fetch(api(`/preview?url=${encodeURIComponent(url)}`));
			if (res.ok) {
				const data = await res.json();
				previewStreamUrl = data.stream_url;
			}
		} catch (e) {
			console.error('Preview failed:', e);
		} finally {
			previewLoading = false;
		}
	}

	function closePreview() {
		showPreview = false;
		previewStreamUrl = '';
	}

	function clearSearch() {
		query = '';
		localResults = [];
		ytResults = [];
	}
</script>

<svelte:head>
	<title>HomeKaraoke — Search</title>
</svelte:head>

<div class="relative z-10 min-h-screen p-4 pb-24">
	<!-- Header -->
	<div class="mb-6 flex items-center gap-3">
		<a
			href="{base}/remote"
			class="glass-light flex h-9 w-9 items-center justify-center rounded-full text-sm"
			style="color: var(--color-dim)"
		>
			&#8592;
		</a>
		<h1 class="gradient-text text-2xl font-bold" style="font-family: var(--font-display)">
			Search Songs
		</h1>
	</div>

	<!-- Search input -->
	<form class="glass mb-4 flex items-center gap-3 rounded-2xl px-4 py-3" onsubmit={onSearchSubmit}>
		<span style="color: var(--color-dim); font-size: 1.1rem">&#128269;</span>
		<input
			type="text"
			placeholder="Search songs..."
			bind:value={query}
			oninput={onInput}
			class="flex-1 bg-transparent text-base outline-none placeholder:opacity-40"
			style="color: var(--color-text); font-family: var(--font-body)"
			autocomplete="off"
		/>
		{#if query}
			<button type="button" onclick={clearSearch}
				class="h-6 w-6 rounded-full text-xs" style="color: var(--color-dim); background: rgba(255,255,255,0.08)"
				aria-label="Clear">&#10005;</button>
		{/if}
		<button type="submit" disabled={!query.trim() || isSearchingYT}
			class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
			style="background: linear-gradient(135deg, var(--color-purple), var(--color-teal)); color: #fff; opacity: {query.trim() ? 1 : 0.4}">
			{isSearchingYT ? 'Searching...' : 'YouTube'}
		</button>
	</form>

	<!-- Options -->
	<div class="mb-4 flex items-center gap-4 px-1 text-xs" style="color: var(--color-dim)">
		<label class="flex items-center gap-1.5">
			<input type="checkbox" bind:checked={autoQueue} class="accent-purple-500" />
			Auto-queue on download
		</label>
	</div>

	<!-- Local Library results -->
	{#if localResults.length > 0}
		<section class="mb-6">
			<div class="mb-2 flex items-center gap-2">
				<h2 class="text-xs font-semibold uppercase tracking-wider" style="color: var(--color-dim)">
					Local Library
				</h2>
				<span class="text-xs" style="color: var(--color-faint)">{localResults.length}</span>
			</div>
			<ul class="flex flex-col gap-1">
				{#each localResults as result (result.path)}
					<li class="glass-light flex items-center gap-3 rounded-xl px-3 py-2">
						<span class="min-w-0 flex-1 truncate text-sm" style="color: var(--color-text)">{result.fileName}</span>
						{#if addedSongs.has(result.path)}
							<span class="text-xs" style="color: var(--color-green)">&#10003;</span>
						{:else}
							<button onclick={() => addToQueue(result.path, result.fileName)}
								class="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold"
								style="background: rgba(124,58,237,0.2); color: var(--color-purple)">+ Queue</button>
						{/if}
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	<!-- YouTube Results -->
	{#if isSearchingYT}
		<div class="glass-light rounded-xl p-8 text-center">
			<div class="search-spinner mx-auto mb-3"></div>
			<p class="text-sm" style="color: var(--color-dim)">Searching YouTube for "{query}"...</p>
		</div>
	{:else if ytResults.length > 0}
		<section>
			<div class="mb-3 flex items-center gap-2">
				<h2 class="text-xs font-semibold uppercase tracking-wider" style="color: var(--color-dim)">YouTube Results</h2>
				<span class="text-xs" style="color: var(--color-faint)">{ytResults.length}</span>
			</div>
			<div class="flex flex-col gap-3">
				{#each ytResults as yt (yt.id)}
					<div class="glass-light overflow-hidden rounded-xl">
						<!-- Thumbnail + preview -->
						<button class="yt-thumb-wrap" onclick={() => openPreview(yt.url)} aria-label="Preview">
							<img src={yt.thumbnail} alt={yt.title} class="yt-thumb" loading="lazy" />
							<div class="yt-play-icon">&#9654;</div>
							{#if yt.duration}
								<span class="yt-duration">{yt.duration}</span>
							{/if}
						</button>
						<!-- Info + download -->
						<div class="flex items-center gap-3 px-3 py-2">
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium" style="color: var(--color-text)">{yt.title}</div>
								{#if yt.channel}
									<div class="text-xs" style="color: var(--color-faint)">{yt.channel}</div>
								{/if}
							</div>
							{#if downloadedUrls.has(yt.url)}
								<span class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
									style="background: rgba(34,197,94,0.15); color: var(--color-green)">&#10003; Done</span>
							{:else if downloadingUrls.has(yt.url)}
								<span class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
									style="background: rgba(245,158,11,0.15); color: var(--color-amber)">...</span>
							{:else}
								<button onclick={() => downloadSong(yt.url, yt.title)}
									class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-opacity active:opacity-70"
									style="background: linear-gradient(135deg, var(--color-purple), var(--color-teal)); color: #fff">
									Download
								</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</section>
	{:else if !query}
		<div class="glass-light rounded-xl p-6 text-center">
			<p class="text-sm" style="color: var(--color-dim)">Type a song name and press "YouTube" to search</p>
		</div>
	{/if}
</div>

<!-- Video preview modal -->
{#if showPreview}
	<div class="preview-overlay" onclick={closePreview} role="dialog">
		<div class="preview-modal glass" onclick={(e) => e.stopPropagation()}>
			<button class="preview-close" onclick={closePreview} aria-label="Close">&#10005;</button>
			{#if previewLoading}
				<div class="p-8 text-center"><div class="search-spinner mx-auto"></div></div>
			{:else if previewStreamUrl}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video src={previewStreamUrl} controls autoplay class="preview-video"></video>
			{:else}
				<div class="p-8 text-center text-sm" style="color: var(--color-dim)">Preview unavailable</div>
			{/if}
		</div>
	</div>
{/if}

<!-- Toast notification -->
<TabBar />

{#if toastMsg}
	<div class="toast glass">
		{toastMsg}
	</div>
{/if}

<style>
	.search-spinner {
		width: 14px; height: 14px;
		border: 2px solid rgba(124, 58, 237, 0.25);
		border-top-color: var(--color-purple);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	.yt-thumb-wrap {
		position: relative; display: block; width: 100%; aspect-ratio: 16/9;
		cursor: pointer; overflow: hidden; border: none; padding: 0; background: #000;
	}
	.yt-thumb { width: 100%; height: 100%; object-fit: cover; transition: opacity 0.2s; }
	.yt-thumb-wrap:hover .yt-thumb { opacity: 0.7; }
	.yt-play-icon {
		position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
		width: 48px; height: 48px; border-radius: 50%;
		background: rgba(0,0,0,0.6); color: #fff; font-size: 18px;
		display: flex; align-items: center; justify-content: center;
		opacity: 0.8; transition: opacity 0.2s;
	}
	.yt-thumb-wrap:hover .yt-play-icon { opacity: 1; }
	.yt-duration {
		position: absolute; bottom: 4px; right: 4px;
		background: rgba(0,0,0,0.8); color: #fff;
		font-size: 0.7rem; padding: 1px 4px; border-radius: 3px;
		font-family: var(--font-mono);
	}

	.preview-overlay {
		position: fixed; inset: 0; z-index: 200;
		background: rgba(0,0,0,0.7); display: flex;
		align-items: center; justify-content: center; padding: 16px;
	}
	.preview-modal {
		position: relative; width: 100%; max-width: 640px;
		border-radius: 16px; overflow: hidden;
	}
	.preview-close {
		position: absolute; top: 8px; right: 8px; z-index: 10;
		width: 32px; height: 32px; border-radius: 50%;
		background: rgba(0,0,0,0.6); color: #fff; border: none;
		font-size: 14px; cursor: pointer;
		display: flex; align-items: center; justify-content: center;
	}
	.preview-video { width: 100%; display: block; }

	.toast {
		position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
		z-index: 100; padding: 10px 20px; font-size: 0.875rem;
		font-weight: 500; color: var(--color-text); white-space: nowrap;
		animation: fadeInUp 0.2s ease;
	}
	@keyframes fadeInUp {
		from { opacity: 0; transform: translateX(-50%) translateY(8px); }
		to { opacity: 1; transform: translateX(-50%) translateY(0); }
	}
</style>
