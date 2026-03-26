<script lang="ts">
	/**
	 * Stem mixer — swipe up/down on icons to control per-stem volume.
	 * Tap to toggle mute. Icon fills from bottom to top based on volume.
	 */
	import { getState } from '$lib/stores/playback.svelte';
	import { emit } from '$lib/stores/socket.svelte';

	let { compact = false }: { compact?: boolean } = $props();

	const np = $derived(getState());

	const allStems = [
		{ name: 'drums', iconClass: 'fa-solid fa-drum', label: 'Drums' },
		{ name: 'bass', iconClass: 'ti ti-wave-sine', label: 'Bass' },
		{ name: 'other', iconClass: 'ti ti-music', label: 'Other' },
		{ name: 'vocals', iconClass: 'fa-solid fa-microphone', label: 'Vocals' },
		{ name: 'lead_vocals', iconClass: 'fa-solid fa-microphone', label: 'Lead' },
		{ name: 'backing_vocals', iconClass: 'fa-solid fa-users', label: 'Backing' },
		{ name: 'guitar', iconClass: 'fa-solid fa-guitar', label: 'Guitar' },
		{ name: 'piano', iconClass: 'ti ti-piano', label: 'Piano' },
	] as const;

	const stems = $derived(
		np.stem_urls
			? allStems.filter((s) => s.name in np.stem_urls)
			: allStems.filter((s) => s.name !== 'lead_vocals' && s.name !== 'backing_vocals'),
	);

	const hasSplitVocals = $derived(np.stem_urls && 'lead_vocals' in np.stem_urls);

	function getVolume(name: string): number {
		const v = np.stem_mix[name];
		if (v === undefined || v === true) return 1.0;
		if (v === false) return 0.0;
		return Number(v);
	}

	function setVolume(name: string, vol: number) {
		const clamped = Math.max(0, Math.min(1, Math.round(vol * 20) / 20));
		emit('stem_volume', { stem: name, volume: clamped });
	}

	function toggleMute(name: string) {
		emit('stem_toggle', name);
	}

	type Preset = 'karaoke' | 'original' | 'practice';

	function applyPreset(preset: Preset) {
		for (const s of stems) {
			let targetVol = 1.0;
			if (preset === 'karaoke') {
				targetVol = (s.name === 'vocals' || s.name === 'lead_vocals') ? 0.0 : 1.0;
			} else if (preset === 'practice') {
				targetVol = (s.name === 'vocals' || s.name === 'lead_vocals') ? 0.3 : 1.0;
			}
			if (getVolume(s.name) !== targetVol) {
				setVolume(s.name, targetVol);
			}
		}
	}

	function handlePointerDown(e: PointerEvent, name: string) {
		e.preventDefault();
		const el = e.currentTarget as HTMLElement;
		el.setPointerCapture(e.pointerId);
		const startY = e.clientY;
		const startVol = getVolume(name);
		let moved = false;

		const onMove = (me: PointerEvent) => {
			const dy = startY - me.clientY; // up = positive
			if (Math.abs(dy) > 4) moved = true;
			if (moved) {
				setVolume(name, startVol + dy / 80);
			}
		};

		const onUp = () => {
			el.removeEventListener('pointermove', onMove);
			el.removeEventListener('pointerup', onUp);
			el.removeEventListener('pointercancel', onUp);
			if (!moved) toggleMute(name);
		};

		el.addEventListener('pointermove', onMove);
		el.addEventListener('pointerup', onUp);
		el.addEventListener('pointercancel', onUp);
	}
</script>

{#if np.stem_separation_enabled}
	<div class="mixer" class:compact>
		{#if np.stems_available}
			<div class="presets">
				<button class="preset-btn" onclick={() => applyPreset('karaoke')} title={hasSplitVocals ? 'Lead OFF, backing ON' : 'Vocals OFF'}>
					<i class="ti ti-microphone-off"></i>
					{#if !compact}<span>Karaoke</span>{/if}
				</button>
				<button class="preset-btn" onclick={() => applyPreset('original')} title="All stems full">
					<i class="ti ti-music"></i>
					{#if !compact}<span>Original</span>{/if}
				</button>
				<button class="preset-btn" onclick={() => applyPreset('practice')} title="Lead vocals at 30%">
					<i class="ti ti-headphones"></i>
					{#if !compact}<span>Practice</span>{/if}
				</button>
			</div>

			<div class="stem-row">
				{#each stems as stem}
					{@const vol = getVolume(stem.name)}
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div
						class="stem-btn"
						class:muted={vol === 0}
						onpointerdown={(e) => handlePointerDown(e, stem.name)}
						title="{stem.label}: {Math.round(vol * 100)}%"
					>
						<div class="stem-icon-wrap">
							<i class="{stem.iconClass} stem-icon-bg"></i>
							<i class="{stem.iconClass} stem-icon-fill" style="clip-path: inset({100 - vol * 100}% 0 0 0)"></i>
						</div>
						<span class="stem-label">{stem.label}</span>
					</div>
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
							{#each Array(np.stem_progress?.total ?? 8) as _, i}
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
		cursor: ns-resize;
		touch-action: none;
		user-select: none;
		transition: opacity 0.15s;
	}
	.stem-btn.muted {
		opacity: 0.4;
	}

	.stem-icon-wrap {
		position: relative;
		width: 1.4em;
		height: 1.4em;
		font-size: 1.2rem;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.stem-icon-bg {
		position: absolute;
		color: rgba(255, 255, 255, 0.15);
	}

	.stem-icon-fill {
		position: absolute;
		color: var(--color-teal);
		transition: clip-path 0.1s ease-out;
	}

	.stem-label {
		font-size: 0.55rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-dim);
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

	.compact .presets { gap: 4px; }
	.compact .preset-btn { padding: 3px 6px; font-size: 0.65rem; }
	.compact .stem-btn { padding: 4px; }
	.compact .stem-icon-wrap { font-size: 1rem; }
	.compact .stem-label { display: none; }
</style>
