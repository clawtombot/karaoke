<script lang="ts">
	/**
	 * Compact stem mixer — icon-only toggle row + quick presets.
	 * Used on both phone remote and splash screen overlay.
	 */
	import { getState } from '$lib/stores/playback.svelte';

	let { onToggle, compact = false }: { onToggle: (stem: string) => void; compact?: boolean } = $props();

	const np = $derived(getState());

	const stems = [
		{ name: 'drums', iconClass: 'fa-solid fa-drum', label: 'Drums' },
		{ name: 'bass', iconClass: 'ti ti-wave-sine', label: 'Bass' },
		{ name: 'other', iconClass: 'ti ti-music', label: 'Other' },
		{ name: 'vocals', iconClass: 'fa-solid fa-microphone', label: 'Vocals' },
		{ name: 'guitar', iconClass: 'fa-solid fa-guitar', label: 'Guitar' },
		{ name: 'piano', iconClass: 'ti ti-piano', label: 'Piano' },
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
						<i class="{stem.iconClass}"></i>
						<span class="stem-dot" class:on={isEnabled(stem.name)}></span>
					</button>
				{/each}
			</div>
		{:else if np.now_playing}
			<div class="stem-pending">
				{#if np.stem_progress?.error}
					<i class="ti ti-alert-triangle" style="color: var(--color-pink)"></i>
					<span>Split failed</span>
				{:else}
					<div class="split-progress">
						<div class="split-bar">
							{#each Array(np.stem_progress?.total ?? 6) as _, i}
								<div class="split-seg" class:done={i < (np.stem_progress?.ready ?? 0)}></div>
							{/each}
						</div>
						<span class="split-label">Splitting stems{np.stem_progress ? ` ${np.stem_progress.ready}/${np.stem_progress.total}` : ''}</span>
					</div>
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
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		color: var(--color-faint);
		font-family: var(--font-mono);
		width: 100%;
	}
	.split-progress {
		display: flex;
		flex-direction: column;
		gap: 4px;
		width: 100%;
	}
	.split-bar {
		display: flex;
		gap: 3px;
		height: 4px;
	}
	.split-seg {
		flex: 1;
		border-radius: 2px;
		background: rgba(255, 255, 255, 0.08);
		transition: background 0.4s, box-shadow 0.4s;
	}
	.split-seg.done {
		background: var(--color-teal);
		box-shadow: 0 0 6px rgba(0, 210, 255, 0.4);
	}
	.split-label {
		font-size: 0.6rem;
		color: var(--color-faint);
		text-align: center;
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
