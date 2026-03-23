<script lang="ts">
	/**
	import { api } from '$lib/api';
	 * Search page — local library search with debounced autocomplete.
	 * YouTube search is a placeholder pending backend JSON endpoint.
	 */
	import { onMount } from 'svelte';
	import Cookies from 'js-cookie';

	interface LocalResult {
		path: string;
		fileName: string;
		type: string;
	}

	let query = $state('');
	let localResults: LocalResult[] = $state([]);
	let isSearching = $state(false);
	let addedSongs = $state(new Set<string>());
	let toastMsg = $state('');
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

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
			isSearching = false;
			return;
		}
		isSearching = true;
		debounceTimer = setTimeout(doSearch, 300);
	}

	async function doSearch() {
		const q = query.trim();
		if (!q) return;
		try {
			const res = await fetch(`/autocomplete?q=${encodeURIComponent(q)}`);
			if (res.ok) {
				localResults = await res.json();
			}
		} catch (e) {
			console.error('[search] autocomplete failed:', e);
		} finally {
			isSearching = false;
		}
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
				showToast(`Added: ${label}`);
			} else {
				showToast('Failed to add song');
			}
		} catch (e) {
			console.error('[search] enqueue failed:', e);
			showToast('Failed to add song');
		}
	}

	function clearSearch() {
		query = '';
		localResults = [];
		isSearching = false;
	}
</script>

<svelte:head>
	<title>HomeKaraoke — Search</title>
</svelte:head>

<div class="relative z-10 min-h-screen p-4 pb-20">
	<!-- Header -->
	<div class="mb-6 flex items-center gap-3">
		<a
			href="/"
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
	<div class="glass mb-6 flex items-center gap-3 rounded-2xl px-4 py-3">
		<span style="color: var(--color-dim); font-size: 1.1rem">&#128269;</span>
		<input
			type="text"
			placeholder="Search your library..."
			bind:value={query}
			oninput={onInput}
			class="flex-1 bg-transparent text-base outline-none placeholder:opacity-40"
			style="color: var(--color-text); font-family: var(--font-body)"
			autocomplete="off"
			autocorrect="off"
			spellcheck="false"
		/>
		{#if query}
			<button
				onclick={clearSearch}
				class="h-6 w-6 rounded-full text-xs"
				style="color: var(--color-dim); background: rgba(255,255,255,0.08)"
				aria-label="Clear search"
			>
				&#10005;
			</button>
		{/if}
	</div>

	<!-- Local Library results -->
	<section class="mb-8">
		<div class="mb-3 flex items-center gap-2">
			<h2 class="text-sm font-semibold uppercase tracking-wider" style="color: var(--color-dim)">
				Local Library
			</h2>
			{#if isSearching}
				<div class="search-spinner"></div>
			{:else if query && localResults.length > 0}
				<span class="text-xs" style="color: var(--color-faint)">{localResults.length} results</span>
			{/if}
		</div>

		{#if !query}
			<div class="glass-light rounded-xl p-6 text-center">
				<p class="text-sm" style="color: var(--color-dim)">Start typing to search your library</p>
			</div>
		{:else if isSearching}
			<div class="glass-light rounded-xl p-6 text-center">
				<p class="text-sm" style="color: var(--color-dim)">Searching...</p>
			</div>
		{:else if localResults.length === 0}
			<div class="glass-light rounded-xl p-6 text-center">
				<p class="text-sm" style="color: var(--color-dim)">No local songs found for "{query}"</p>
			</div>
		{:else}
			<ul class="flex flex-col gap-2">
				{#each localResults as result (result.path)}
					<li class="glass-light flex items-center gap-3 rounded-xl px-4 py-3">
						<!-- Type badge -->
						<span
							class="shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold font-mono uppercase"
							style="background: rgba(124,58,237,0.18); color: var(--color-purple)"
						>
							{result.type || 'mp4'}
						</span>
						<!-- Title -->
						<span class="min-w-0 flex-1 truncate text-sm font-medium" style="color: var(--color-text)">
							{result.fileName}
						</span>
						<!-- Add button -->
						{#if addedSongs.has(result.path)}
							<span
								class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
								style="background: rgba(34,197,94,0.15); color: var(--color-green)"
							>
								&#10003; Added
							</span>
						{:else}
							<button
								onclick={() => addToQueue(result.path, result.fileName)}
								class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-opacity active:opacity-70"
								style="background: linear-gradient(135deg, var(--color-purple), var(--color-teal)); color: #fff"
							>
								+ Queue
							</button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<!-- YouTube Search — placeholder -->
	<section>
		<div class="mb-3 flex items-center gap-2">
			<h2 class="text-sm font-semibold uppercase tracking-wider" style="color: var(--color-dim)">
				YouTube
			</h2>
			<span
				class="rounded px-1.5 py-0.5 text-xs font-mono"
				style="background: rgba(245,158,11,0.15); color: var(--color-amber)"
			>
				Coming Soon
			</span>
		</div>
		<div class="glass-light rounded-xl p-6 text-center">
			<p class="mb-1 text-sm font-medium" style="color: var(--color-dim)">
				YouTube search requires a backend JSON endpoint
			</p>
			<p class="text-xs" style="color: var(--color-faint)">
				Use the TV display to search and queue YouTube songs for now.
			</p>
		</div>
	</section>
</div>

<!-- Toast notification -->
{#if toastMsg}
	<div class="toast glass">
		{toastMsg}
	</div>
{/if}

<style>
	.search-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid rgba(124, 58, 237, 0.25);
		border-top-color: var(--color-purple);
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.toast {
		position: fixed;
		bottom: 24px;
		left: 50%;
		transform: translateX(-50%);
		z-index: 100;
		padding: 10px 20px;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--color-text);
		white-space: nowrap;
		animation: fadeInUp 0.2s ease;
	}

	@keyframes fadeInUp {
		from {
			opacity: 0;
			transform: translateX(-50%) translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateX(-50%) translateY(0);
		}
	}
</style>
