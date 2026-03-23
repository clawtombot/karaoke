<script lang="ts">
	/**
	 * Compact stem mixer — icon-only toggle row + quick presets.
	 * Used on both phone remote and splash screen overlay.
	 */
	import { getState } from '$lib/stores/playback.svelte';

	let { onToggle, compact = false }: { onToggle: (stem: string) => void; compact?: boolean } = $props();

	const np = $derived(getState());

	const stems = [
		{ name: 'drums', icon: 'ti-arrows-shuffle', label: 'Drums' },
		{ name: 'bass', icon: 'ti-wave-sine', label: 'Bass' },
		{ name: 'other', icon: 'ti-waveform', label: 'Other' },
		{ name: 'vocals', icon: 'ti-microphone-2', label: 'Vocals' },
		{ name: 'guitar', icon: 'ti-guitar-pick', label: 'Guitar' },
		{ name: 'piano', icon: 'ti-piano', label: 'Piano' },
	] as const;

	type Preset = 'karaoke' | 'original' | 'practice';

	function applyPreset(preset: Preset) {
		const presetMix: Record<string, boolean> = {};
		for (const s of stems) {
			if (preset === 'karaoke') {
				presetMix[s.name] = s.name !== 'vocals';
			} else if (preset === 'original') {
				presetMix[s.name] = true;
			} else if (preset === 'practice') {
				presetMix[s.name] = true; // All on, but vocals at 30% handled by volume
			}
		}
		// Toggle each stem that needs to change
		for (const [name, shouldBeOn] of Object.entries(presetMix)) {
			if ((np.stem_mix[name] ?? true) !== shouldBeOn) {
				onToggle(name);
			}
		}
	}

	function isEnabled(name: string): boolean {
		return np.stem_mix[name] ?? true;
	}
</script>

{#if np.vocal_splitter_enabled}
	<div class="mixer" class:compact>
		{#if np.stems_available}
			<!-- Quick presets -->
			<div class="presets">
				<button class="preset-btn" on:click={() => applyPreset('karaoke')} title="Vocals OFF">
					<i class="ti ti-microphone-off"></i>
					{#if !compact}<span>Karaoke</span>{/if}
				</button>
				<button class="preset-btn" on:click={() => applyPreset('original')} title="All stems ON">
					<i class="ti ti-music"></i>
					{#if !compact}<span>Original</span>{/if}
				</button>
				<button class="preset-btn" on:click={() => applyPreset('practice')} title="Vocals low">
					<i class="ti ti-headphones"></i>
					{#if !compact}<span>Practice</span>{/if}
				</button>
			</div>

			<!-- Individual stem toggles -->
			<div class="stem-row">
				{#each stems as stem}
					<button
						class="stem-btn"
						class:active={isEnabled(stem.name)}
						on:click={() => onToggle(stem.name)}
						title={stem.label}
					>
						<i class="ti {stem.icon}"></i>
						<span class="stem-dot" class:on={isEnabled(stem.name)}></span>
					</button>
				{/each}
			</div>
		{:else if np.now_playing}
			<div class="stem-pending">
				{#if np.stem_progress?.error}
					Stem splitting failed
				{:else if np.stem_progress}
					Splitting... {np.stem_progress.ready}/{np.stem_progress.total}
				{:else}
					Processing stems...
				{/if}
			</div>
		{/if}
	</div>
{/if}

<style>
	.mixer {
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: center;
	}

	.presets {
		display: flex;
		gap: 6px;
	}

	.preset-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 5px 10px;
		border-radius: 8px;
		border: 1px solid var(--color-border2);
		background: var(--color-surface);
		color: var(--color-dim);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}
	.preset-btn:hover {
		background: var(--color-surface2);
		color: var(--color-text);
		border-color: rgba(124, 58, 237, 0.4);
	}
	.preset-btn i {
		font-size: 0.9rem;
	}

	.stem-row {
		display: flex;
		gap: 10px;
		justify-content: center;
	}

	.stem-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 3px;
		padding: 6px;
		border: none;
		background: transparent;
		color: var(--color-faint);
		cursor: pointer;
		transition: color 0.15s;
		font-size: 1.2rem;
	}
	.stem-btn.active {
		color: var(--color-teal);
	}
	.stem-btn:hover {
		color: var(--color-text);
	}

	.stem-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: var(--color-faint);
		transition: background 0.15s;
	}
	.stem-dot.on {
		background: var(--color-teal);
		box-shadow: 0 0 6px rgba(0, 210, 255, 0.5);
	}

	.stem-pending {
		font-size: 0.75rem;
		color: var(--color-faint);
		font-family: var(--font-mono);
	}

	/* Compact mode for splash overlay */
	.compact .presets {
		gap: 4px;
	}
	.compact .preset-btn {
		padding: 3px 6px;
		font-size: 0.65rem;
	}
	.compact .stem-btn {
		font-size: 1rem;
		padding: 4px;
	}
</style>
