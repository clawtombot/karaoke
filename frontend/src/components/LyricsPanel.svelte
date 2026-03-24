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

	// Only highlight words if we have real YRC word-level timing
	const hasRealTiming = $derived(lyrics?.has_word_timing ?? false);

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
		// Position current line ~30% from top (past lines visible above)
		const targetY = containerRect.height * 0.3;
		const offset = elRect.top - containerRect.top - targetY;
		container.scrollBy({ top: offset, behavior: 'smooth' });
	});

	function wordClass(lineIsCurrent: boolean, wIdx: number, activeWordIdx: number): string {
		if (!hasRealTiming) return 'lyric-word';
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
		if (!hasRealTiming) return '';
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
							<span class="lyric-word" class:sung={hasRealTiming && state !== 'future'}>{line.text}</span>
						</div>
						{#if line.romanized}
							<div class="line-romanized">{line.romanized}</div>
						{/if}
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

	/* Position current line near top with 1 past above */
	.lines-list {
		-webkit-perspective: 1000px;
		perspective: 1000px;
		padding-top: 25%;
		padding-bottom: 0;
	}

	.scroll-spacer {
		height: 60%;
	}

	.lyrics-line {
		padding: 8px 8px;
		text-align: left;
		cursor: default;
		user-select: none;
		transition: opacity 0.25s ease;
	}

	.lyrics-line.current {
		opacity: 1;
	}

	.lyrics-line.past {
		opacity: 0.2;
	}

	.lyrics-line.future {
		opacity: 0.35;
	}

	.line-text {
		font-family: var(--font-display);
		font-size: 1.8rem;
		font-weight: 700;
		line-height: 1.4;
		letter-spacing: 0.01em;
		word-break: break-word;
		transform-origin: left top;
		/* iOS Safari: pre-promote to GPU layer to prevent ghosting */
		will-change: transform;
		-webkit-backface-visibility: hidden;
		backface-visibility: hidden;
		-webkit-font-smoothing: antialiased;
		transform: scale(1) translateZ(0);
		transition: transform 0.25s ease;
	}

	.lyrics-line.past .line-text,
	.lyrics-line.future .line-text {
		transform: scale(0.75) translateZ(0);
	}

	.line-romanized {
		font-size: 0.7rem;
		color: var(--color-teal, #00d2ff);
		margin-top: 2px;
		opacity: 0.7;
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
