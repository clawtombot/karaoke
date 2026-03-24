<script lang="ts">
	/**
	 * LyricsPanel — scrollable synced lyrics for phone remote view.
	 * Shows current line highlighted, previous dimmed, future dimmed.
	 * Auto-scrolls to keep current line centered.
	 * Renders romaji via <ruby> for CJK lines.
	 */
	import { onMount } from 'svelte';
	import {
		getLyrics,
		getCurrentLineIndex,
		getCurrentWordIndex,
		getWordProgress,
		updatePosition,
		type LyricsLine,
	} from '$lib/stores/lyrics.svelte';

	let { currentTimeMs = 0 }: { currentTimeMs: number } = $props();

	const lyrics = $derived(getLyrics());
	const lineIdx = $derived(getCurrentLineIndex());
	const wordIdx = $derived(getCurrentWordIndex());
	const progress = $derived(getWordProgress());

	// Update position every frame via effect
	$effect(() => {
		updatePosition(currentTimeMs);
	});

	// Container ref for auto-scroll
	let container: HTMLDivElement;
	// Line element refs by index
	let lineRefs: Record<number, HTMLDivElement> = {};

	// Auto-scroll: keep active line centered when it changes
	$effect(() => {
		const idx = lineIdx;
		if (idx < 0 || !container) return;
		const el = lineRefs[idx];
		if (!el) return;

		const containerRect = container.getBoundingClientRect();
		const elRect = el.getBoundingClientRect();
		const offset = elRect.top - containerRect.top - containerRect.height / 2 + elRect.height / 2;
		container.scrollBy({ top: offset, behavior: 'smooth' });
	});

	function wordClass(lineIsCurrent: boolean, wIdx: number, activeWordIdx: number): string {
		if (!lineIsCurrent) return 'lyric-word';
		if (wIdx < activeWordIdx) return 'lyric-word sung';
		if (wIdx === activeWordIdx) return 'lyric-word active';
		return 'lyric-word';
	}

	function wordStyle(
		lineIsCurrent: boolean,
		wIdx: number,
		activeWordIdx: number,
		prog: number
	): string {
		if (lineIsCurrent && wIdx === activeWordIdx) {
			return `--progress: ${Math.round(prog * 100)}%`;
		}
		return '';
	}

	function lineState(idx: number): 'past' | 'current' | 'future' {
		if (idx < lineIdx) return 'past';
		if (idx === lineIdx) return 'current';
		return 'future';
	}
</script>

<div class="lyrics-panel" bind:this={container}>
	{#if !lyrics || lyrics.lines.length === 0}
		<div class="empty-state">
			<i class="ti ti-music-off empty-icon"></i>
			<span>No lyrics available</span>
		</div>
	{:else}
		<div class="lines-list">
			{#each lyrics.lines as line, idx}
				{@const state = lineState(idx)}
				<div
					class="lyrics-line"
					class:current={state === 'current'}
					class:past={state === 'past'}
					class:future={state === 'future'}
					bind:this={lineRefs[idx]}
				>
					{#if line.words && line.words.length > 0}
						<div class="line-text">
							{#each line.words as word, wIdx}
								{@const needsSpace = wIdx < line.words.length - 1 && !/^[,.\-!?;:)）」』】]/.test(line.words[wIdx + 1]?.text ?? '')}
								{#if line.romanized}
									<ruby
										class={wordClass(state === 'current', wIdx, wordIdx)}
										style={wordStyle(state === 'current', wIdx, wordIdx, progress)}
									>{word.text}<rt>{line.romanized.split(/\s+/)[wIdx] ?? ''}</rt></ruby>{needsSpace ? ' ' : ''}
								{:else}
									<span
										class={wordClass(state === 'current', wIdx, wordIdx)}
										style={wordStyle(state === 'current', wIdx, wordIdx, progress)}
									>{word.text}</span>{needsSpace ? ' ' : ''}
								{/if}
							{/each}
						</div>
					{:else}
						<div class="line-text">
							<span class="lyric-word" class:sung={state !== 'future'}>{line.text}</span>
						</div>
					{/if}

					{#if line.translated && state === 'current'}
						<div class="line-translation">{line.translated}</div>
					{/if}
				</div>
			{/each}
			<!-- Spacer so last line can scroll to center -->
			<div class="scroll-spacer"></div>
		</div>
	{/if}
</div>

<style>
	.lyrics-panel {
		width: 100%;
		height: 100%;
		overflow-y: auto;
		overflow-x: hidden;
		scroll-behavior: smooth;
		-webkit-overflow-scrolling: touch;
		/* Hide scrollbar */
		scrollbar-width: none;
		-ms-overflow-style: none;
	}
	.lyrics-panel::-webkit-scrollbar {
		display: none;
	}

	/* Padding so the first/last lines can be centered */
	.lines-list {
		padding-top: 30%;
		padding-bottom: 0;
	}

	.scroll-spacer {
		height: 30%;
	}

	.lyrics-line {
		padding: 6px 16px;
		text-align: center;
		transition: opacity 0.3s ease, transform 0.3s ease;
		cursor: default;
		user-select: none;
	}

	.lyrics-line.current {
		opacity: 1;
		transform: scale(1.04);
	}

	.lyrics-line.past {
		opacity: 0.28;
		transform: scale(0.97);
	}

	.lyrics-line.future {
		opacity: 0.38;
		transform: scale(0.97);
	}

	.line-text {
		font-family: var(--font-display);
		font-size: 1.05rem;
		font-weight: 600;
		line-height: 1.55;
		letter-spacing: 0.01em;
		word-break: break-word;
	}

	.lyrics-line.current .line-text {
		font-size: 1.15rem;
		font-weight: 700;
	}

	.line-translation {
		font-family: var(--font-body);
		font-size: 0.75rem;
		color: var(--color-dim);
		margin-top: 3px;
		font-style: italic;
	}

	/* Ruby spacing */
	ruby {
		ruby-position: over;
	}

	ruby > :global(rt) {
		font-size: 0.5em;
		color: var(--color-dim);
		font-family: var(--font-mono);
	}

	.empty-state {
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 10px;
		color: var(--color-faint);
		font-size: 0.85rem;
		font-family: var(--font-body);
	}

	.empty-icon {
		font-size: 2rem;
		opacity: 0.5;
	}
</style>
