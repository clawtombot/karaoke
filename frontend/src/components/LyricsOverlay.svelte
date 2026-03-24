<script lang="ts">
	/**
	 * TV Splash lyrics overlay — word-by-word gradient highlight with romaji.
	 * Positioned at bottom 30% of screen over the video player.
	 */
	import { onMount, onDestroy } from 'svelte';
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

	// Update lyrics position on every frame
	$effect(() => {
		updatePosition(currentTimeMs);
	});

	// Get the lines to display: current + next
	const displayLines = $derived.by(() => {
		if (!lyrics?.lines) return [];
		const lines: { line: LyricsLine; isCurrent: boolean }[] = [];

		if (lineIdx >= 0) {
			lines.push({ line: lyrics.lines[lineIdx], isCurrent: true });
		}
		// Next line preview
		const nextIdx = lineIdx >= 0 ? lineIdx + 1 : 0;
		if (nextIdx < lyrics.lines.length) {
			lines.push({ line: lyrics.lines[nextIdx], isCurrent: false });
		}
		return lines;
	});

	function wordClass(
		lineIsCurrent: boolean,
		wIdx: number,
		activeWordIdx: number
	): string {
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
</script>

{#if lyrics && lyrics.lines.length > 0}
	<div class="lyrics-overlay">
		{#each displayLines as { line, isCurrent }, i (lineIdx + i)}
			<div
				class="lyrics-line"
				class:current={isCurrent}
				class:preview={!isCurrent}
			>
				{#if line.romanized && isCurrent}
					<div class="lyrics-romanized">{line.romanized}</div>
				{/if}

				<div class="lyrics-text">
					{#if line.words && line.words.length > 0}
						{#each line.words as word, wIdx}
							{@const needsSpace = wIdx < line.words.length - 1 && !/^[,.\-!?;:)）」』】]/.test(line.words[wIdx + 1]?.text ?? '')}
							{#if line.romanized}
								<ruby
									class={wordClass(isCurrent, wIdx, wordIdx)}
									style={wordStyle(isCurrent, wIdx, wordIdx, progress)}
								>{word.text}<rt></rt></ruby>{needsSpace ? ' ' : ''}
							{:else}
								<span
									class={wordClass(isCurrent, wIdx, wordIdx)}
									style={wordStyle(isCurrent, wIdx, wordIdx, progress)}
								>{word.text}</span>{needsSpace ? ' ' : ''}
							{/if}
						{/each}
					{:else}
						<span class="lyric-word" class:sung={isCurrent}>{line.text}</span>
					{/if}
				</div>

				{#if line.translated && isCurrent}
					<div class="lyrics-translation">{line.translated}</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<style>
	.lyrics-overlay {
		position: absolute;
		bottom: 12%;
		left: 50%;
		transform: translateX(-50%);
		width: 85%;
		z-index: 5;
		text-align: center;
		pointer-events: none;
	}

	.lyrics-line {
		margin-bottom: 0.5rem;
		transition: opacity 0.3s ease;
	}

	.lyrics-line.current {
		opacity: 1;
	}

	.lyrics-line.preview {
		opacity: 0.35;
	}

	.lyrics-text {
		font-family: var(--font-display);
		font-size: 2.8rem;
		font-weight: 700;
		line-height: 1.3;
		letter-spacing: 0.02em;
		filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.9)) drop-shadow(0 0 20px rgba(0, 0, 0, 0.7));
	}

	.lyrics-line.preview .lyrics-text {
		font-size: 1.8rem;
		font-weight: 600;
	}

	.lyrics-romanized {
		font-family: var(--font-mono);
		font-size: 1.1rem;
		color: var(--color-dim);
		margin-bottom: 0.25rem;
		letter-spacing: 0.08em;
		filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.8));
	}

	.lyrics-translation {
		font-family: var(--font-body);
		font-size: 1rem;
		color: var(--color-dim);
		margin-top: 0.25rem;
		font-style: italic;
		filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.8));
	}

	/* Ruby annotations for CJK */
	ruby {
		ruby-position: over;
	}
	ruby > :global(rt) {
		font-size: 0.45em;
		color: var(--color-dim);
		font-family: var(--font-mono);
	}
</style>
