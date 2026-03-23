<script lang="ts">
	/**
	 * Browse page — paginated song library with letter filter, sort, edit, delete.
	 */
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import Cookies from 'js-cookie';

	interface BrowseResponse {
		songs: string[];
		total: number;
		page: number;
		per_page: number;
	}

	let songs: string[] = $state([]);
	let total = $state(0);
	let page = $state(1);
	let perPage = $state(100);
	let activeLetter: string | null = $state(null);
	let sortMode: 'name' | 'date' = $state('name');
	let isLoading = $state(true);

	// Edit modal state
	let editSong = $state('');
	let editRawStem = $state('');
	let editNewName = $state('');
	let showEdit = $state(false);
	let editLoading = $state(false);
	let editError = $state('');
	let suggestions: string[] = $state([]);
	let suggestLoading = $state(false);

	// Delete confirm
	let confirmDeleteSong = $state('');

	// Toast
	let toastMsg = $state('');
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	// Queue tracking
	let addedSongs = $state(new Set<string>());

	const alphabet = '#ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

	function showToast(msg: string) {
		toastMsg = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toastMsg = ''), 2500);
	}

	function songName(path: string): string {
		const file = path.split('/').pop() ?? path;
		return file.replace(/\.[^.]+$/, '').replace(/---[A-Za-z0-9_-]{11}$/, '').replace(/ \[[A-Za-z0-9_-]{11}\]$/, '');
	}

	async function fetchSongs() {
		isLoading = true;
		try {
			const params = new URLSearchParams({ page: String(page) });
			if (activeLetter) {
				params.set('letter', activeLetter === '#' ? 'numeric' : activeLetter.toLowerCase());
			}
			if (sortMode === 'date') params.set('sort', 'date');

			const res = await fetch(api(`/browse?${params}`));
			if (res.ok) {
				const data: BrowseResponse = await res.json();
				songs = data.songs;
				total = data.total;
				perPage = data.per_page;
			}
		} catch (e) {
			console.error('[browse] fetch failed:', e);
		} finally {
			isLoading = false;
		}
	}

	function selectLetter(letter: string | null) {
		activeLetter = letter;
		page = 1;
		fetchSongs();
	}

	function toggleSort() {
		sortMode = sortMode === 'name' ? 'date' : 'name';
		page = 1;
		fetchSongs();
	}

	function goPage(p: number) {
		page = p;
		fetchSongs();
	}

	async function addToQueue(path: string) {
		const user = Cookies.get('user') ?? 'Guest';
		try {
			const res = await fetch(api('/enqueue'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ song: path, user }),
			});
			if (res.ok) {
				addedSongs = new Set([...addedSongs, path]);
				showToast(`Queued: ${songName(path)}`);
			}
		} catch {
			showToast('Failed to queue');
		}
	}

	async function openEdit(path: string) {
		editLoading = true;
		editError = '';
		editSong = path;
		showEdit = true;
		suggestions = [];
		try {
			const res = await fetch(api(`/files/edit?song=${encodeURIComponent(path)}`));
			const data = await res.json();
			if (data.ok) {
				editRawStem = data.raw_stem;
				// Get tidy name suggestion
				const tidyRes = await fetch(api(`/metadata/tidy-name?filename=${encodeURIComponent(data.raw_stem)}`));
				if (tidyRes.ok) {
					const tidy = await tidyRes.json();
					editNewName = tidy.tidied;
				} else {
					editNewName = data.raw_stem;
				}
			} else {
				editError = data.error ?? 'Cannot edit this song';
			}
		} catch {
			editError = 'Failed to load song info';
		} finally {
			editLoading = false;
		}
	}

	async function loadSuggestions() {
		if (!editRawStem) return;
		suggestLoading = true;
		try {
			const res = await fetch(api(`/metadata/suggest-names?filename=${encodeURIComponent(editRawStem)}&limit=5`));
			if (res.ok) {
				const data = await res.json();
				suggestions = data.suggestions ?? [];
			}
		} catch {
			// ignore
		} finally {
			suggestLoading = false;
		}
	}

	async function saveEdit() {
		if (!editNewName.trim()) return;
		editLoading = true;
		editError = '';
		try {
			const res = await fetch(api('/files/edit'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ old_file_name: editSong, new_file_name: editNewName.trim() }),
			});
			const data = await res.json();
			if (data.ok) {
				showEdit = false;
				showToast('Song renamed');
				fetchSongs();
			} else {
				editError = data.error ?? 'Rename failed';
			}
		} catch {
			editError = 'Rename request failed';
		} finally {
			editLoading = false;
		}
	}

	async function deleteSong(path: string) {
		try {
			const res = await fetch(api(`/files/delete?song=${encodeURIComponent(path)}`));
			const data = await res.json();
			if (data.ok) {
				showToast('Song deleted');
				confirmDeleteSong = '';
				fetchSongs();
			} else {
				showToast(data.error ?? 'Delete failed');
			}
		} catch {
			showToast('Delete request failed');
		}
	}

	$effect(() => {
		fetchSongs();
	});

	const totalPages = $derived(Math.ceil(total / perPage));
</script>

<svelte:head>
	<title>HomeKaraoke — Browse</title>
</svelte:head>

<div class="relative z-10 min-h-screen pb-20">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 pt-4 pb-2">
		<div class="flex items-center gap-3">
			<a
				href="{base}/remote"
				class="glass-light flex h-9 w-9 items-center justify-content rounded-full text-sm"
				style="color: var(--color-dim); display: flex; align-items: center; justify-content: center"
			>
				&#8592;
			</a>
			<h1 class="gradient-text text-2xl font-bold" style="font-family: var(--font-display)">
				Browse
			</h1>
			{#if total > 0}
				<span
					class="rounded-full px-2 py-0.5 text-xs font-semibold font-mono"
					style="background: rgba(124,58,237,0.18); color: var(--color-purple)"
				>
					{total}
				</span>
			{/if}
		</div>
		<button
			onclick={toggleSort}
			class="glass-light rounded-xl px-3 py-2 text-xs font-semibold transition-opacity active:opacity-70"
			style="color: var(--color-teal)"
		>
			{sortMode === 'name' ? 'A-Z' : 'Recent'}
		</button>
	</div>

	<!-- Alphabet strip -->
	<div class="alpha-strip">
		<button
			class="alpha-btn"
			class:active={activeLetter === null}
			onclick={() => selectLetter(null)}
		>All</button>
		{#each alphabet as letter}
			<button
				class="alpha-btn"
				class:active={activeLetter === letter}
				onclick={() => selectLetter(letter)}
			>{letter}</button>
		{/each}
	</div>

	<!-- Song list -->
	<div class="px-4 mt-2">
		{#if isLoading}
			<div class="glass-light rounded-xl p-6 text-center">
				<div class="search-spinner mx-auto mb-3"></div>
				<p class="text-sm" style="color: var(--color-dim)">Loading songs...</p>
			</div>
		{:else if songs.length === 0}
			<div class="glass-light rounded-xl p-8 text-center">
				<p class="mb-1 text-sm font-medium" style="color: var(--color-dim)">No songs found</p>
				<p class="text-xs" style="color: var(--color-faint)">
					{activeLetter ? `No songs starting with "${activeLetter}"` : 'Download some songs first'}
				</p>
			</div>
		{:else}
			<ul class="flex flex-col gap-1.5">
				{#each songs as song, i (song)}
					<li class="glass-light rounded-xl px-3 py-2.5">
						<div class="flex items-center gap-3">
							<!-- Song number -->
							<span class="shrink-0 text-xs font-mono" style="color: var(--color-faint); min-width: 24px; text-align: right">
								{(page - 1) * perPage + i + 1}
							</span>

							<!-- Song name -->
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium" style="color: var(--color-text)">
									{songName(song)}
								</div>
							</div>

							<!-- Actions -->
							<div class="flex shrink-0 items-center gap-1">
								{#if addedSongs.has(song)}
									<span class="text-xs" style="color: var(--color-green)">&#10003;</span>
								{:else}
									<button
										onclick={() => addToQueue(song)}
										class="action-btn"
										aria-label="Queue"
										title="Add to queue"
									>
										&#9654;
									</button>
								{/if}
								<button
									onclick={() => openEdit(song)}
									class="action-btn"
									aria-label="Edit"
									title="Rename"
								>
									&#9998;
								</button>
								{#if confirmDeleteSong === song}
									<button
										onclick={() => deleteSong(song)}
										class="action-btn delete-confirm"
										aria-label="Confirm delete"
									>
										&#10003;
									</button>
									<button
										onclick={() => (confirmDeleteSong = '')}
										class="action-btn"
										aria-label="Cancel"
									>
										&#10005;
									</button>
								{:else}
									<button
										onclick={() => (confirmDeleteSong = song)}
										class="action-btn delete-btn"
										aria-label="Delete"
										title="Delete"
									>
										&#128465;
									</button>
								{/if}
							</div>
						</div>
					</li>
				{/each}
			</ul>

			<!-- Pagination -->
			{#if totalPages > 1}
				<div class="pagination">
					<button
						disabled={page <= 1}
						onclick={() => goPage(page - 1)}
						class="page-btn"
					>&#8592;</button>
					<span class="page-info">
						{page} / {totalPages}
					</span>
					<button
						disabled={page >= totalPages}
						onclick={() => goPage(page + 1)}
						class="page-btn"
					>&#8594;</button>
				</div>
			{/if}
		{/if}
	</div>
</div>

<!-- Edit/Rename modal -->
{#if showEdit}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
	<div class="modal-overlay" onclick={() => (showEdit = false)} role="dialog" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (showEdit = false)}>
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="modal glass" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-bold" style="color: var(--color-text)">Rename Song</h2>
				<button onclick={() => (showEdit = false)} class="modal-close" aria-label="Close">&#10005;</button>
			</div>

			{#if editLoading && !editNewName}
				<div class="p-4 text-center"><div class="search-spinner mx-auto"></div></div>
			{:else if editError && !editNewName}
				<p class="text-sm" style="color: var(--color-pink)">{editError}</p>
			{:else}
				<div class="mb-3">
					<label class="block text-xs font-semibold mb-1 uppercase tracking-wider" style="color: var(--color-dim)">Current</label>
					<div class="text-sm truncate" style="color: var(--color-faint)">{editRawStem}</div>
				</div>

				<div class="mb-3">
					<label class="block text-xs font-semibold mb-1 uppercase tracking-wider" style="color: var(--color-dim)">New Name</label>
					<input
						type="text"
						bind:value={editNewName}
						class="w-full rounded-lg px-3 py-2 text-sm outline-none"
						style="background: rgba(255,255,255,0.08); border: 1px solid var(--color-border2); color: var(--color-text); font-family: var(--font-body)"
					/>
				</div>

				{#if editError}
					<p class="mb-3 text-xs" style="color: var(--color-pink)">{editError}</p>
				{/if}

				<!-- Last.fm suggestions -->
				<div class="mb-4">
					<button
						onclick={loadSuggestions}
						disabled={suggestLoading}
						class="text-xs font-semibold"
						style="color: var(--color-teal)"
					>
						{suggestLoading ? 'Loading...' : 'Last.fm suggestions'}
					</button>
					{#if suggestions.length > 0}
						<ul class="mt-2 flex flex-col gap-1">
							{#each suggestions as s}
								<li>
									<button
										onclick={() => (editNewName = s)}
										class="glass-light w-full rounded-lg px-3 py-1.5 text-left text-xs truncate transition-opacity active:opacity-70"
										style="color: var(--color-text)"
									>{s}</button>
								</li>
							{/each}
						</ul>
					{/if}
				</div>

				<div class="flex gap-2">
					<button
						onclick={() => (showEdit = false)}
						class="flex-1 glass-light rounded-xl px-4 py-2 text-sm font-semibold"
						style="color: var(--color-dim)"
					>Cancel</button>
					<button
						onclick={saveEdit}
						disabled={editLoading || !editNewName.trim()}
						class="flex-1 rounded-xl px-4 py-2 text-sm font-semibold text-white"
						style="background: linear-gradient(135deg, var(--color-purple), var(--color-teal)); opacity: {editNewName.trim() ? 1 : 0.4}"
					>{editLoading ? 'Saving...' : 'Save'}</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

<!-- Tab bar -->
<nav class="tab-bar">
	<a href="{base}/remote" class="tab"><i class="ti ti-home-2"></i><span>Home</span></a>
	<a href="{base}/search" class="tab"><i class="ti ti-search"></i><span>Search</span></a>
	<a href="{base}/browse" class="tab active"><i class="ti ti-music"></i><span>Browse</span></a>
	<a href="{base}/queue" class="tab"><i class="ti ti-list-numbers"></i><span>Queue</span></a>
</nav>

<!-- Toast -->
{#if toastMsg}
	<div class="toast glass">{toastMsg}</div>
{/if}

<style>
	.alpha-strip {
		display: flex;
		gap: 2px;
		padding: 4px 8px;
		overflow-x: auto;
		scrollbar-width: none;
		-webkit-overflow-scrolling: touch;
	}
	.alpha-strip::-webkit-scrollbar { display: none; }
	.alpha-btn {
		flex-shrink: 0;
		width: 28px;
		height: 28px;
		border-radius: 6px;
		border: none;
		background: rgba(255, 255, 255, 0.05);
		color: var(--color-faint);
		font-size: 0.7rem;
		font-weight: 600;
		font-family: var(--font-mono);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.1s, color 0.1s;
	}
	.alpha-btn:hover { background: rgba(255, 255, 255, 0.1); color: var(--color-text); }
	.alpha-btn.active {
		background: linear-gradient(135deg, var(--color-purple), var(--color-teal));
		color: #fff;
	}

	.action-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 8px;
		font-size: 0.8rem;
		background: rgba(255, 255, 255, 0.05);
		color: var(--color-dim);
		border: 1px solid rgba(255, 255, 255, 0.07);
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
	}
	.action-btn:hover { background: rgba(255, 255, 255, 0.1); color: var(--color-text); }
	.delete-btn:hover { background: rgba(236, 72, 153, 0.15); color: var(--color-pink); }
	.delete-confirm {
		background: rgba(236, 72, 153, 0.2) !important;
		color: var(--color-pink) !important;
		border-color: var(--color-pink) !important;
	}

	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 16px 0;
	}
	.page-btn {
		width: 36px;
		height: 36px;
		border-radius: 10px;
		border: 1px solid var(--color-border2);
		background: var(--color-surface);
		color: var(--color-text);
		font-size: 1rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.page-btn:disabled { opacity: 0.25; cursor: not-allowed; }
	.page-btn:hover:not(:disabled) { background: var(--color-surface2); }
	.page-info {
		font-family: var(--font-mono);
		font-size: 0.8rem;
		color: var(--color-dim);
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 200;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 16px;
	}
	.modal {
		width: 100%;
		max-width: 440px;
		padding: 20px;
	}
	.modal-close {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.08);
		color: var(--color-dim);
		border: none;
		font-size: 14px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}

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

	.tab-bar {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 50;
		display: flex;
		justify-content: space-around;
		padding: 8px 0 env(safe-area-inset-bottom, 8px);
		background: rgba(8, 4, 18, 0.95);
		backdrop-filter: blur(20px);
		-webkit-backdrop-filter: blur(20px);
		border-top: 1px solid var(--color-border);
	}
	.tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		padding: 4px 16px;
		color: var(--color-faint);
		text-decoration: none;
		font-size: 0.6rem;
		font-weight: 600;
	}
	.tab i {
		font-size: 1.2rem;
	}
	.tab:hover,
	.tab.active {
		color: var(--color-teal);
	}

	.toast {
		position: fixed;
		bottom: 80px;
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
		from { opacity: 0; transform: translateX(-50%) translateY(8px); }
		to { opacity: 1; transform: translateX(-50%) translateY(0); }
	}
</style>
