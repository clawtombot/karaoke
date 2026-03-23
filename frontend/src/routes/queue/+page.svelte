<script lang="ts">
	/**
	 * Queue management page — view, reorder, and manage the song queue.
	 * Real-time updates via Socket.IO queue_update event.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import { on } from '$lib/stores/socket.svelte';
	import { getState } from '$lib/stores/playback.svelte';

	interface QueueItem {
		file: string;
		title: string;
		user: string;
		semitones: number;
	}

	const np = $derived(getState());

	let queue: QueueItem[] = $state([]);
	let isLoading = $state(true);
	let confirmClear = $state(false);
	let confirmTimer: ReturnType<typeof setTimeout> | null = null;
	let toastMsg = $state('');
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	// Drag state
	let dragIndex: number | null = $state(null);
	let dragOverIndex: number | null = $state(null);

	let unsubs: Array<() => void> = [];

	function showToast(msg: string) {
		toastMsg = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toastMsg = ''), 2500);
	}

	async function fetchQueue() {
		try {
			const res = await fetch(api('/get_queue'));
			if (res.ok) {
				queue = await res.json();
			}
		} catch (e) {
			console.error('[queue] fetch failed:', e);
		} finally {
			isLoading = false;
		}
	}

	async function editQueue(action: string, song: string) {
		try {
			await fetch(api(`/queue/edit?action=${encodeURIComponent(action)}&song=${encodeURIComponent(song)}`));
			await fetchQueue();
		} catch (e) {
			console.error('[queue] edit failed:', e);
		}
	}

	async function reorder(oldIndex: number, newIndex: number) {
		if (oldIndex === newIndex) return;
		// Optimistic update
		const updated = [...queue];
		const [moved] = updated.splice(oldIndex, 1);
		updated.splice(newIndex, 0, moved);
		queue = updated;

		try {
			await fetch(api('/queue/reorder'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ old_index: oldIndex, new_index: newIndex }),
			});
		} catch (e) {
			console.error('[queue] reorder failed:', e);
			await fetchQueue(); // Revert on error
		}
	}

	async function addRandom() {
		try {
			await fetch(api('/queue/addrandom/5'));
			await fetchQueue();
			showToast('Added 5 random songs');
		} catch (e) {
			console.error('[queue] addrandom failed:', e);
		}
	}

	function requestClear() {
		confirmClear = true;
		if (confirmTimer) clearTimeout(confirmTimer);
		confirmTimer = setTimeout(() => (confirmClear = false), 4000);
	}

	async function confirmClearQueue() {
		confirmClear = false;
		if (confirmTimer) clearTimeout(confirmTimer);
		try {
			await fetch(api('/queue/edit?action=clear'));
			await fetchQueue();
			showToast('Queue cleared');
		} catch (e) {
			console.error('[queue] clear failed:', e);
		}
	}

	// Drag & drop handlers
	function onDragStart(e: DragEvent, index: number) {
		dragIndex = index;
		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move';
			e.dataTransfer.setData('text/plain', String(index));
		}
	}

	function onDragOver(e: DragEvent, index: number) {
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
		dragOverIndex = index;
	}

	function onDragLeave() {
		dragOverIndex = null;
	}

	function onDrop(e: DragEvent, index: number) {
		e.preventDefault();
		if (dragIndex !== null && dragIndex !== index) {
			reorder(dragIndex, index);
		}
		dragIndex = null;
		dragOverIndex = null;
	}

	function onDragEnd() {
		dragIndex = null;
		dragOverIndex = null;
	}

	onMount(() => {
		fetchQueue();

		unsubs = [
			on('queue_update', () => {
				fetchQueue();
			}),
		];

		return () => unsubs.forEach((fn) => fn());
	});

	onDestroy(() => {
		if (confirmTimer) clearTimeout(confirmTimer);
		if (toastTimer) clearTimeout(toastTimer);
	});

	function songLabel(item: QueueItem): string {
		return item.title || item.file.split('/').pop()?.replace(/\.[^.]+$/, '') || item.file;
	}

	function keyLabel(semitones: number): string {
		if (!semitones) return '';
		return semitones > 0 ? `+${semitones}` : String(semitones);
	}
</script>

<svelte:head>
	<title>HomeKaraoke — Queue</title>
</svelte:head>

<div class="relative z-10 min-h-screen p-4 pb-24">
	<!-- Header -->
	<div class="mb-6 flex items-center justify-between">
		<div class="flex items-center gap-3">
			<a
				href="{base}/remote"
				class="glass-light flex h-9 w-9 items-center justify-center rounded-full text-sm"
				style="color: var(--color-dim)"
			>
				&#8592;
			</a>
			<h1 class="gradient-text text-2xl font-bold" style="font-family: var(--font-display)">
				Queue
			</h1>
			{#if queue.length > 0}
				<span
					class="rounded-full px-2 py-0.5 text-xs font-semibold font-mono"
					style="background: rgba(124,58,237,0.18); color: var(--color-purple)"
				>
					{queue.length}
				</span>
			{/if}
		</div>

		<!-- Actions -->
		<div class="flex items-center gap-2">
			<button
				onclick={addRandom}
				class="glass-light rounded-xl px-3 py-2 text-xs font-semibold transition-opacity active:opacity-70"
				style="color: var(--color-teal)"
			>
				+ Random
			</button>
			{#if confirmClear}
				<button
					onclick={confirmClearQueue}
					class="rounded-xl px-3 py-2 text-xs font-semibold transition-opacity active:opacity-70"
					style="background: rgba(236,72,153,0.2); color: var(--color-pink)"
				>
					Confirm Clear?
				</button>
			{:else}
				<button
					onclick={requestClear}
					class="glass-light rounded-xl px-3 py-2 text-xs font-semibold transition-opacity active:opacity-70"
					style="color: var(--color-dim)"
					disabled={queue.length === 0}
				>
					Clear All
				</button>
			{/if}
		</div>
	</div>

	<!-- Now Playing -->
	{#if np.now_playing}
		<div class="glass mb-4 rounded-2xl p-4" style="border-color: rgba(0,210,255,0.25)">
			<div class="mb-1 flex items-center gap-2">
				<span
					class="rounded px-1.5 py-0.5 text-xs font-semibold font-mono uppercase"
					style="background: rgba(0,210,255,0.15); color: var(--color-teal)"
				>
					LIVE
				</span>
				{#if np.now_playing_transpose !== 0}
					<span
						class="rounded px-1.5 py-0.5 text-xs font-semibold font-mono"
						style="background: rgba(34,197,94,0.15); color: var(--color-green)"
					>
						Key {keyLabel(np.now_playing_transpose)}
					</span>
				{/if}
			</div>
			<div class="mb-0.5 truncate text-base font-semibold" style="color: var(--color-text)">
				{np.now_playing}
			</div>
			<div class="text-sm" style="color: var(--color-teal)">
				{np.now_playing_user ?? ''}
			</div>
			<!-- Progress bar -->
			{#if np.now_playing_duration && np.now_playing_position !== null}
				<div
					class="mt-3 h-1 overflow-hidden rounded-full"
					style="background: rgba(255,255,255,0.1)"
				>
					<div
						class="h-full rounded-full transition-all"
						style="width: {(np.now_playing_position / np.now_playing_duration) * 100}%; background: linear-gradient(90deg, var(--color-purple), var(--color-teal))"
					></div>
				</div>
			{/if}
		</div>
	{/if}

	<!-- Up next label -->
	{#if queue.length > 0}
		<div class="mb-2 text-xs font-semibold uppercase tracking-wider" style="color: var(--color-dim)">
			Up Next
		</div>
	{/if}

	<!-- Queue list -->
	{#if isLoading}
		<div class="glass-light rounded-xl p-6 text-center">
			<p class="text-sm" style="color: var(--color-dim)">Loading queue...</p>
		</div>
	{:else if queue.length === 0}
		<div class="glass-light rounded-xl p-8 text-center">
			<p class="mb-1 text-sm font-medium" style="color: var(--color-dim)">Queue is empty</p>
			<p class="text-xs" style="color: var(--color-faint)">
				Search for songs or tap "+ Random" to add some.
			</p>
		</div>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each queue as item, i (item.file + i)}
				<li
					draggable="true"
					ondragstart={(e) => onDragStart(e, i)}
					ondragover={(e) => onDragOver(e, i)}
					ondragleave={onDragLeave}
					ondrop={(e) => onDrop(e, i)}
					ondragend={onDragEnd}
					class="queue-item glass-light flex items-center gap-3 rounded-xl px-3 py-3 transition-all"
					class:drag-over={dragOverIndex === i && dragIndex !== i}
					class:dragging={dragIndex === i}
				>
					<!-- Drag handle + position -->
					<div class="flex shrink-0 flex-col items-center">
						<span class="drag-handle mb-0.5 cursor-grab select-none text-base leading-none" style="color: var(--color-faint)">
							&#8942;&#8942;
						</span>
						<span
							class="text-xs font-semibold font-mono"
							style="color: var(--color-faint)"
						>
							{i + 1}
						</span>
					</div>

					<!-- Song info -->
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-semibold" style="color: var(--color-text)">
							{songLabel(item)}
						</div>
						<div class="flex items-center gap-2 mt-0.5">
							<span class="text-xs" style="color: var(--color-teal)">{item.user}</span>
							{#if item.semitones}
								<span
									class="rounded px-1 py-0.5 text-xs font-mono"
									style="background: rgba(34,197,94,0.12); color: var(--color-green)"
								>
									{keyLabel(item.semitones)}
								</span>
							{/if}
						</div>
					</div>

					<!-- Action buttons -->
					<div class="flex shrink-0 items-center gap-1">
						<button
							onclick={() => editQueue('up', item.file)}
							class="queue-btn"
							aria-label="Move up"
							disabled={i === 0}
						>
							&#8593;
						</button>
						<button
							onclick={() => editQueue('down', item.file)}
							class="queue-btn"
							aria-label="Move down"
							disabled={i === queue.length - 1}
						>
							&#8595;
						</button>
						<button
							onclick={() => editQueue('delete', item.file)}
							class="queue-btn delete-btn"
							aria-label="Remove"
						>
							&#10005;
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<!-- Toast -->
{#if toastMsg}
	<div class="toast glass">
		{toastMsg}
	</div>
{/if}

<style>
	.queue-item {
		transition:
			opacity 0.15s,
			transform 0.15s,
			border-color 0.15s;
	}

	.queue-item.dragging {
		opacity: 0.4;
	}

	.queue-item.drag-over {
		border-color: rgba(0, 210, 255, 0.4);
		transform: scale(1.01);
	}

	.drag-handle {
		letter-spacing: -3px;
		color: var(--color-faint);
	}

	.queue-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 8px;
		font-size: 0.85rem;
		background: rgba(255, 255, 255, 0.05);
		color: var(--color-dim);
		border: 1px solid rgba(255, 255, 255, 0.07);
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
	}

	.queue-btn:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.1);
		color: var(--color-text);
	}

	.queue-btn:disabled {
		opacity: 0.25;
		cursor: not-allowed;
	}

	.delete-btn:hover:not(:disabled) {
		background: rgba(236, 72, 153, 0.15);
		color: var(--color-pink);
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
