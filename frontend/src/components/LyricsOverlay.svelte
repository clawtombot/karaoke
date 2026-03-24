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

	// Show lines in pairs: (0,1), (2,3), (4,5)...
	// First line fills, then second line fills, then swap to fresh pair.
	const pairStart = $derived(lineIdx >= 0 ? Math.floor(lineIdx / 2) * 2 : 0);

	const displayLines = $derived.by(() => {
		if (!lyrics?.lines) return [];
		const lines: { line: LyricsLine; lineIndex: number }[] = [];
		const total = lyrics.lines.length;

		if (pairStart < total) {
			lines.push({ line: lyrics.lines[pairStart], lineIndex: pairStart });
		}
		if (pairStart + 1 < total) {
			lines.push({ line: lyrics.lines[pairStart + 1], lineIndex: pairStart + 1 });
		}
		return lines;
	});

	// Only highlight words if we have real YRC word-level timing
	const hasRealTiming = $derived(lyrics?.has_word_timing ?? false);

	function wordClass(
		isActiveLine: boolean,
		isSungLine: boolean,
		wIdx: number,
		activeWordIdx: number
	): string {
		if (!hasRealTiming) return 'lyric-word';
		if (isSungLine) return 'lyric-word sung';
		if (!isActiveLine) return 'lyric-word';
		if (wIdx < activeWordIdx) return 'lyric-word sung';
		if (wIdx === activeWordIdx) return 'lyric-word active';
		return 'lyric-word';
	}

	function wordStyle(
		isActiveLine: boolean,
		wIdx: number,
		activeWordIdx: number,
		prog: number
	): string {
		if (!hasRealTiming) return '';
		if (isActiveLine && wIdx === activeWordIdx) {
			return `--progress: ${Math.round(prog * 100)}%`;
		}
		return '';
	}
</script>

{#if lyrics && lyrics.lines.length > 0}
	<div class="lyrics-overlay">
		{#each displayLines as { line, lineIndex }, i (pairStart + i)}
			{@const isActive = lineIndex === lineIdx}
			{@const isSung = lineIndex < lineIdx}
			<div class="lyrics-line">
				{#if line.romanized && isActive}
					<div class="lyrics-romanized">{line.romanized}</div>
				{/if}

				<div class="lyrics-text">
					{#if line.words && line.words.length > 0}
						{#each line.words as word, wIdx}
							{@const needsSpace = wIdx < line.words.length - 1 && !/^[,.\-!?;:)）」』】]/.test(line.words[wIdx + 1]?.text ?? '')}
							{#if line.romanized}
								<ruby
									class={wordClass(isActive, isSung, wIdx, wordIdx)}
									style={wordStyle(isActive, wIdx, wordIdx, progress)}
								>{word.text}<rt></rt></ruby>{needsSpace ? ' ' : ''}
							{:else}
								<span
									class={wordClass(isActive, isSung, wIdx, wordIdx)}
									style={wordStyle(isActive, wIdx, wordIdx, progress)}
								>{word.text}</span>{needsSpace ? ' ' : ''}
							{/if}
						{/each}
					{:else}
						<span class="lyric-word" class:sung={isSung || isActive}>{line.text}</span>
					{/if}
				</div>

				{#if line.translated && isActive}
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


	.lyrics-text {
		font-family: var(--font-display);
		font-size: 2.8rem;
		font-weight: 700;
		line-height: 1.3;
		letter-spacing: 0.02em;
		filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.9)) drop-shadow(0 0 20px rgba(0, 0, 0, 0.7));
	}


	.lyrics-romanized {
		font-family: var(--font-display);
		font-size: 1.6rem;
		font-weight: 700;
		color: #fff;
		margin-bottom: 0.3rem;
		letter-spacing: 0.04em;
		filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.9)) drop-shadow(0 0 12px rgba(0, 0, 0, 0.6));
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
