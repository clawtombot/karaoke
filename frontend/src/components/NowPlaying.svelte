<script lang="ts">
	/**
	 * Reusable now-playing card — shows current song, singer, progress, key badge.
	 */
	import { getState } from '$lib/stores/playback.svelte';

	const np = $derived(getState());

	function formatTime(seconds: number | null): string {
		if (!seconds || isNaN(seconds)) return '00:00';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	const progressPct = $derived(
		np.now_playing_duration && np.now_playing_position
			? Math.min(100, (np.now_playing_position / np.now_playing_duration) * 100)
			: 0
	);
</script>

<div class="glass np-card">
	<div class="np-header">
		<div class="np-icon">
			{#if np.now_playing}
				<i class="ti ti-music" style="color: var(--color-teal); font-size: 1.4rem"></i>
			{:else}
				<i class="ti ti-music-off" style="color: var(--color-faint); font-size: 1.4rem"></i>
			{/if}
		</div>
		<div class="np-info">
			<div class="np-title">{np.now_playing ?? 'Nothing playing'}</div>
			<div class="np-singer">
				{#if np.now_playing}
					<i class="ti ti-microphone-2"></i> {np.now_playing_user ?? ''}
				{:else}
					Queue a song to get started
				{/if}
			</div>
		</div>
		{#if np.now_playing_transpose !== 0}
			<span class="np-key-badge">
				{np.now_playing_transpose > 0 ? '+' : ''}{np.now_playing_transpose}
			</span>
		{/if}
		{#if np.now_playing}
			<span class="np-live"><span class="np-live-dot"></span> LIVE</span>
		{/if}
	</div>

	{#if np.now_playing}
		<div class="np-progress-wrap">
			<div class="np-progress-track">
				<div class="np-progress-fill" style="width: {progressPct}%"></div>
			</div>
			<div class="np-time">
				<span>{formatTime(np.now_playing_position)}</span>
				<span>{formatTime(np.now_playing_duration)}</span>
			</div>
		</div>
	{/if}
</div>

<style>
	.np-card {
		padding: 14px;
		border-radius: 16px;
	}

	.np-header {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.np-icon {
		flex-shrink: 0;
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 10px;
		background: var(--color-surface2);
	}

	.np-info {
		flex: 1;
		min-width: 0;
	}

	.np-title {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 0.95rem;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.np-singer {
		font-size: 0.8rem;
		color: var(--color-teal);
		display: flex;
		align-items: center;
		gap: 3px;
	}

	.np-key-badge {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 6px;
		background: rgba(34, 197, 94, 0.15);
		color: var(--color-green);
		border: 1px solid rgba(34, 197, 94, 0.3);
	}

	.np-live {
		display: flex;
		align-items: center;
		gap: 4px;
		font-size: 0.6rem;
		font-weight: 700;
		color: var(--color-pink);
		letter-spacing: 0.08em;
	}

	.np-live-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--color-pink);
		animation: pulse 1.5s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	.np-progress-wrap {
		margin-top: 10px;
	}

	.np-progress-track {
		height: 3px;
		background: rgba(255, 255, 255, 0.1);
		border-radius: 2px;
		overflow: hidden;
	}

	.np-progress-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--color-purple), var(--color-teal));
		border-radius: 2px;
		transition: width 0.5s linear;
	}

	.np-time {
		display: flex;
		justify-content: space-between;
		margin-top: 4px;
		font-family: var(--font-mono);
		font-size: 0.65rem;
		color: var(--color-faint);
	}
</style>
