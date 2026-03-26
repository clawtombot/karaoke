<script lang="ts">
	/**
	 * Settings page — system info, preferences toggles, admin actions.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { api } from '$lib/api';

	interface SelectOption {
		value: string;
		label: string;
		description: string;
	}

	interface StemSeparationInfo {
		enabled: boolean;
		backend: string;
		device: string;
		model: string;
		vocal_model: string;
		model_cache_dir: string;
		options: {
			backends: SelectOption[];
			devices: Record<string, SelectOption[]>;
			models: SelectOption[];
			vocal_models: SelectOption[];
		};
	}

	interface SystemInfo {
		tommyskaraoke_version: string;
		platform: string;
		os_version: string;
		ffmpeg_version: string;
		youtubedl_version: string;
		is_pi: boolean;
		is_linux: boolean;
		admin: boolean;
		volume: number;
		bg_music_volume: number;
		// Boolean prefs
		hide_url: boolean;
		hide_notifications: boolean;
		high_quality: boolean;
		normalize_audio: boolean;
		complete_transcode_before_play: boolean;
		hide_overlay: boolean;
		disable_bg_music: boolean;
		disable_bg_video: boolean;
		disable_score: boolean;
		enable_fair_queue: boolean;
		cdg_pixel_scaling: boolean;
		show_splash_clock: boolean;
		// Numeric prefs
		splash_delay: number;
		screensaver_timeout: number;
		buffer_size: number;
		avsync: number;
		limit_user_songs_by: number;
		browse_results_per_page: number;
		// Other
		url: string;
		is_transpose_enabled: boolean;
		stem_separation: StemSeparationInfo;
	}

	interface SystemStats {
		cpu: string;
		memory: string;
		disk: string;
	}

	let info: SystemInfo | null = $state(null);
	let stats: SystemStats | null = $state(null);
	let isLoading = $state(true);
	let toastMsg = $state('');
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	// Confirm states for dangerous actions
	let confirmAction = $state('');
	let confirmTimer: ReturnType<typeof setTimeout> | null = null;

	const boolPrefs = [
		{ key: 'high_quality', label: 'High Quality', desc: 'Higher quality video transcoding' },
		{ key: 'normalize_audio', label: 'Normalize Audio', desc: 'Even out volume levels between songs' },
		{ key: 'complete_transcode_before_play', label: 'Full Transcode First', desc: 'Complete transcoding before playback starts' },
		{ key: 'enable_fair_queue', label: 'Fair Queue', desc: 'Alternate between singers in queue' },
		{ key: 'cdg_pixel_scaling', label: 'CDG Pixel Scaling', desc: 'Nearest-neighbor scaling for CDG files' },
		{ key: 'disable_bg_music', label: 'Disable Background Music', desc: 'No music during idle splash screen' },
		{ key: 'disable_bg_video', label: 'Disable Background Video', desc: 'No video during idle splash screen' },
		{ key: 'disable_score', label: 'Disable Scoring', desc: 'Turn off karaoke scoring' },
		{ key: 'show_splash_clock', label: 'Show Clock on Splash', desc: 'Display time on idle TV screen' },
		{ key: 'hide_url', label: 'Hide URL on TV', desc: 'Hide connection URL from TV display' },
		{ key: 'hide_overlay', label: 'Hide TV Overlay', desc: 'Hide now-playing overlay on TV' },
		{ key: 'hide_notifications', label: 'Hide Notifications', desc: 'Suppress toast notifications on TV' },
	];

	const numPrefs = [
		{ key: 'splash_delay', label: 'Splash Delay', unit: 'sec', min: 0, max: 30, step: 1 },
		{ key: 'screensaver_timeout', label: 'Screensaver Timeout', unit: 'sec', min: 0, max: 3600, step: 30 },
		{ key: 'buffer_size', label: 'Buffer Size', unit: 'ms', min: 0, max: 1000, step: 50 },
		{ key: 'avsync', label: 'A/V Sync Offset', unit: 'ms', min: -500, max: 500, step: 10 },
		{ key: 'limit_user_songs_by', label: 'Songs Per User Limit', unit: '', min: 0, max: 50, step: 1 },
		{ key: 'browse_results_per_page', label: 'Browse Per Page', unit: '', min: 10, max: 500, step: 10 },
	];

	function showToast(msg: string) {
		toastMsg = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toastMsg = ''), 2500);
	}

	async function fetchInfo() {
		isLoading = true;
		try {
			const res = await fetch(api('/info'));
			if (res.ok) info = await res.json();
		} catch (e) {
			console.error('[settings] info fetch failed:', e);
		} finally {
			isLoading = false;
		}
	}

	async function fetchStats() {
		try {
			const res = await fetch(api('/info/stats'));
			if (res.ok) stats = await res.json();
		} catch (e) {
			console.error('[settings] stats fetch failed:', e);
		}
	}

	async function changePref(key: string, val: string | boolean | number) {
		try {
			const res = await fetch(api(`/change_preferences?pref=${encodeURIComponent(key)}&val=${encodeURIComponent(String(val))}`));
			const payload = await res.json().catch(() => null);
			const success = res.ok && (!Array.isArray(payload) || payload[0] !== false) && payload?.ok !== false;
			if (success) {
				showToast(`Updated: ${key.replace(/_/g, ' ')}`);
				// Update local state
				if (info && key in info) (info as any)[key] = val;
				return true;
			}
			showToast(Array.isArray(payload) ? payload[1] : (payload?.error ?? 'Failed to update preference'));
		} catch {
			showToast('Failed to update preference');
		}
		return false;
	}

	function toggleBool(key: string) {
		if (!info) return;
		const newVal = !(info as any)[key];
		(info as any)[key] = newVal;
		changePref(key, newVal);
	}

	function onNumChange(key: string, e: Event) {
		const val = (e.target as HTMLInputElement).value;
		changePref(key, val);
	}

	function stemDeviceOptions() {
		if (!info) return [];
		return info.stem_separation.options.devices[info.stem_separation.backend] ?? [];
	}

	async function setStemPref(key: string, val: string | boolean) {
		const ok = await changePref(key, val);
		if (ok) await fetchInfo();
	}

	function requestConfirm(action: string) {
		confirmAction = action;
		if (confirmTimer) clearTimeout(confirmTimer);
		confirmTimer = setTimeout(() => (confirmAction = ''), 4000);
	}

	async function doAction(action: string) {
		confirmAction = '';
		if (confirmTimer) clearTimeout(confirmTimer);
		try {
			const res = await fetch(api(`/${action}`));
			if (res.ok) {
				const data = await res.json();
				showToast(data.message ?? `${action} initiated`);
			}
		} catch {
			showToast(`${action} failed`);
		}
	}

	async function refreshSongs() {
		try {
			await fetch(api('/refresh'));
			showToast('Song list refreshed');
		} catch {
			showToast('Refresh failed');
		}
	}

	async function updateYtdl() {
		try {
			await fetch(api('/update_ytdl'));
			showToast('Updating yt-dlp... this may take a minute');
		} catch {
			showToast('Update failed');
		}
	}

	async function resetPrefs() {
		try {
			const res = await fetch(api('/clear_preferences'));
			if (res.ok) {
				showToast('Preferences reset to defaults');
				await fetchInfo();
			}
		} catch {
			showToast('Reset failed');
		}
	}

	onMount(() => {
		fetchInfo();
		fetchStats();
	});
</script>

<svelte:head>
	<title>TommysKaraoke — Settings</title>
</svelte:head>

<div class="relative z-10 min-h-screen p-4 pb-20">
	<!-- Header -->
	<div class="mb-6 flex items-center gap-3">
		<a
			href="{base}/remote"
			class="glass-light flex h-9 w-9 items-center justify-center rounded-full text-sm"
			style="color: var(--color-dim)"
		>
			&#8592;
		</a>
		<h1 class="gradient-text text-2xl font-bold" style="font-family: var(--font-display)">
			Settings
		</h1>
	</div>

	{#if isLoading}
		<div class="glass-light rounded-xl p-6 text-center">
			<div class="search-spinner mx-auto mb-3"></div>
			<p class="text-sm" style="color: var(--color-dim)">Loading...</p>
		</div>
	{:else if info}
		<!-- System Info -->
		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">System</h2>
			<div class="info-grid">
				<div class="info-item">
					<span class="info-label">Version</span>
					<span class="info-value">{info.tommyskaraoke_version}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Platform</span>
					<span class="info-value">{info.platform}</span>
				</div>
				<div class="info-item">
					<span class="info-label">yt-dlp</span>
					<span class="info-value">{info.youtubedl_version}</span>
				</div>
				<div class="info-item">
					<span class="info-label">FFmpeg</span>
					<span class="info-value">{info.ffmpeg_version}</span>
				</div>
				<div class="info-item">
					<span class="info-label">URL</span>
					<span class="info-value" style="color: var(--color-teal)">{info.url}</span>
				</div>
			</div>
			{#if stats}
				<div class="info-grid mt-3 pt-3" style="border-top: 1px solid var(--color-border)">
					<div class="info-item">
						<span class="info-label">CPU</span>
						<span class="info-value">{stats.cpu}</span>
					</div>
					<div class="info-item">
						<span class="info-label">Memory</span>
						<span class="info-value text-xs">{stats.memory}</span>
					</div>
					<div class="info-item">
						<span class="info-label">Disk</span>
						<span class="info-value text-xs">{stats.disk}</span>
					</div>
				</div>
			{/if}
		</section>

		<!-- Playback Preferences -->
		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">Playback</h2>
			{#each boolPrefs.slice(0, 4) as pref}
				<div class="toggle-row">
					<div class="toggle-info">
						<span class="toggle-label">{pref.label}</span>
						<span class="toggle-desc">{pref.desc}</span>
					</div>
					<button
						class="toggle-switch"
						class:on={(info as any)[pref.key]}
						onclick={() => toggleBool(pref.key)}
						aria-label="Toggle {pref.label}"
					>
						<span class="toggle-knob"></span>
					</button>
				</div>
			{/each}
		</section>

		<!-- Display Preferences -->
		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">Display</h2>
			{#each boolPrefs.slice(4) as pref}
				<div class="toggle-row">
					<div class="toggle-info">
						<span class="toggle-label">{pref.label}</span>
						<span class="toggle-desc">{pref.desc}</span>
					</div>
					<button
						class="toggle-switch"
						class:on={(info as any)[pref.key]}
						onclick={() => toggleBool(pref.key)}
						aria-label="Toggle {pref.label}"
					>
						<span class="toggle-knob"></span>
					</button>
				</div>
			{/each}
		</section>

		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">Stem Separation</h2>
			<p class="section-note">
				Choose the backend and models once for the whole server. Required files download
				automatically on first use.
			</p>
			<div class="toggle-row">
				<div class="toggle-info">
					<span class="toggle-label">Enable Stem Separation</span>
					<span class="toggle-desc">Applies the selected split models to new songs</span>
				</div>
				<button
					class="toggle-switch"
					class:on={info.stem_separation.enabled}
					onclick={() => setStemPref('stem_separation_enabled', !info.stem_separation.enabled)}
					aria-label="Toggle stem separation"
				>
					<span class="toggle-knob"></span>
				</button>
			</div>

			<div class="select-row">
				<div class="toggle-info">
					<span class="toggle-label">First Pass Backend</span>
					<span class="toggle-desc">Pick the runtime that matches this server</span>
				</div>
				<select
					class="select-input"
					value={info.stem_separation.backend}
					onchange={(e) => setStemPref('separation_backend', (e.target as HTMLSelectElement).value)}
				>
					<option value="">Select backend</option>
					{#each info.stem_separation.options.backends as option}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>

			{#if info.stem_separation.backend === 'demucs'}
				<div class="select-row">
					<div class="toggle-info">
						<span class="toggle-label">Execution Device</span>
						<span class="toggle-desc">CPU works anywhere, CUDA is best on NVIDIA hosts</span>
					</div>
					<select
						class="select-input"
						value={info.stem_separation.device}
						onchange={(e) => setStemPref('separation_device', (e.target as HTMLSelectElement).value)}
					>
						<option value="">Select device</option>
						{#each stemDeviceOptions() as option}
							<option value={option.value}>{option.label}</option>
						{/each}
					</select>
				</div>
			{/if}

			<div class="select-row">
				<div class="toggle-info">
					<span class="toggle-label">Stem Separation Model</span>
					<span class="toggle-desc">Primary multistem split used for drums, bass, vocals, and more</span>
				</div>
				<select
					class="select-input"
					value={info.stem_separation.model}
					onchange={(e) => setStemPref('separation_model', (e.target as HTMLSelectElement).value)}
				>
					<option value="">Select stem model</option>
					{#each info.stem_separation.options.models as option}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>

			<div class="select-row">
				<div class="toggle-info">
					<span class="toggle-label">Lead and Backing Vocal Model</span>
					<span class="toggle-desc">Second pass that splits the vocal stem into lead and backing</span>
				</div>
				<select
					class="select-input"
					value={info.stem_separation.vocal_model}
					onchange={(e) => setStemPref('vocal_split_model', (e.target as HTMLSelectElement).value)}
				>
					<option value="">Select vocal model</option>
					{#each info.stem_separation.options.vocal_models as option}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>

			<div class="info-grid mt-3 pt-3" style="border-top: 1px solid var(--color-border)">
				<div class="info-item">
					<span class="info-label">Model Cache</span>
					<span class="info-value text-xs">{info.stem_separation.model_cache_dir || '(default cache)'}</span>
				</div>
			</div>
		</section>

		<!-- Numeric Preferences -->
		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">Advanced</h2>
			{#each numPrefs as pref}
				<div class="num-row">
					<div class="num-info">
						<span class="num-label">{pref.label}</span>
						{#if pref.unit}
							<span class="num-unit">{pref.unit}</span>
						{/if}
					</div>
					<input
						type="number"
						value={(info as any)[pref.key]}
						min={pref.min}
						max={pref.max}
						step={pref.step}
						onchange={(e) => onNumChange(pref.key, e)}
						class="num-input"
					/>
				</div>
			{/each}
		</section>

		<!-- Admin Actions -->
		<section class="glass rounded-2xl p-4 mb-4">
			<h2 class="section-title">Actions</h2>
			<div class="flex flex-col gap-2">
				<button onclick={refreshSongs} class="action-row">
					<span class="action-icon">&#8635;</span>
					<span class="action-text">Refresh Song List</span>
				</button>
				<button onclick={updateYtdl} class="action-row">
					<span class="action-icon">&#8682;</span>
					<span class="action-text">Update yt-dlp</span>
				</button>
				<button onclick={resetPrefs} class="action-row" style="border-color: rgba(245,158,11,0.2)">
					<span class="action-icon" style="color: var(--color-amber)">&#8634;</span>
					<span class="action-text" style="color: var(--color-amber)">Reset All Preferences</span>
				</button>
			</div>
		</section>

		<!-- Danger Zone -->
		<section class="glass rounded-2xl p-4 mb-4" style="border-color: rgba(236,72,153,0.25)">
			<h2 class="section-title" style="color: var(--color-pink)">Danger Zone</h2>
			<div class="flex flex-col gap-2">
				{#if confirmAction === 'quit'}
					<button onclick={() => doAction('quit')} class="danger-btn confirm">
						Confirm: Quit Application?
					</button>
				{:else}
					<button onclick={() => requestConfirm('quit')} class="danger-btn">
						Quit Application
					</button>
				{/if}

				{#if info.is_linux || info.is_pi}
					{#if confirmAction === 'reboot'}
						<button onclick={() => doAction('reboot')} class="danger-btn confirm">
							Confirm: Reboot System?
						</button>
					{:else}
						<button onclick={() => requestConfirm('reboot')} class="danger-btn">
							Reboot System
						</button>
					{/if}

					{#if confirmAction === 'shutdown'}
						<button onclick={() => doAction('shutdown')} class="danger-btn confirm">
							Confirm: Shutdown System?
						</button>
					{:else}
						<button onclick={() => requestConfirm('shutdown')} class="danger-btn">
							Shutdown System
						</button>
					{/if}
				{/if}
			</div>
		</section>
	{/if}
</div>

<!-- Toast -->
{#if toastMsg}
	<div class="toast glass">{toastMsg}</div>
{/if}

<style>
	.section-title {
		font-family: var(--font-mono);
		font-size: 0.65rem;
		color: var(--color-faint);
		letter-spacing: 0.15em;
		text-transform: uppercase;
		margin-bottom: 12px;
	}

	.section-note {
		font-size: 0.75rem;
		line-height: 1.45;
		color: var(--color-faint);
		margin-bottom: 12px;
	}

	.info-grid {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.info-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.info-label {
		font-size: 0.8rem;
		color: var(--color-dim);
	}
	.info-value {
		font-size: 0.8rem;
		font-family: var(--font-mono);
		color: var(--color-text);
	}

	/* Toggle switch */
	.toggle-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}
	.toggle-row:last-child {
		border-bottom: none;
	}
	.toggle-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
		margin-right: 12px;
	}
	.toggle-label {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
	}
	.toggle-desc {
		font-size: 0.7rem;
		color: var(--color-faint);
		margin-top: 1px;
	}
	.toggle-switch {
		position: relative;
		width: 42px;
		height: 24px;
		border-radius: 12px;
		border: none;
		background: rgba(255, 255, 255, 0.1);
		cursor: pointer;
		transition: background 0.2s;
		flex-shrink: 0;
	}
	.toggle-switch.on {
		background: linear-gradient(135deg, var(--color-purple), var(--color-teal));
	}
	.toggle-knob {
		position: absolute;
		top: 2px;
		left: 2px;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: #fff;
		transition: transform 0.2s;
	}
	.toggle-switch.on .toggle-knob {
		transform: translateX(18px);
	}

	.select-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 8px 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}

	.select-input {
		width: 150px;
		max-width: 42%;
		padding: 7px 10px;
		border-radius: 10px;
		border: 1px solid var(--color-border2);
		background: rgba(255, 255, 255, 0.06);
		color: var(--color-text);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		outline: none;
		flex-shrink: 0;
	}

	.select-input:focus {
		border-color: var(--color-purple);
	}

	/* Numeric inputs */
	.num-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}
	.num-row:last-child {
		border-bottom: none;
	}
	.num-info {
		display: flex;
		align-items: baseline;
		gap: 6px;
	}
	.num-label {
		font-size: 0.85rem;
		color: var(--color-text);
	}
	.num-unit {
		font-size: 0.65rem;
		font-family: var(--font-mono);
		color: var(--color-faint);
	}
	.num-input {
		width: 80px;
		padding: 4px 8px;
		border-radius: 8px;
		border: 1px solid var(--color-border2);
		background: rgba(255, 255, 255, 0.06);
		color: var(--color-text);
		font-family: var(--font-mono);
		font-size: 0.8rem;
		text-align: right;
		outline: none;
	}
	.num-input:focus {
		border-color: var(--color-purple);
	}

	/* Action buttons */
	.action-row {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 12px;
		border-radius: 12px;
		border: 1px solid rgba(255, 255, 255, 0.08);
		background: rgba(255, 255, 255, 0.04);
		cursor: pointer;
		transition: background 0.1s;
	}
	.action-row:hover {
		background: rgba(255, 255, 255, 0.08);
	}
	.action-icon {
		font-size: 1.1rem;
		color: var(--color-teal);
	}
	.action-text {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
	}

	/* Danger zone */
	.danger-btn {
		width: 100%;
		padding: 10px 12px;
		border-radius: 12px;
		border: 1px solid rgba(236, 72, 153, 0.15);
		background: rgba(236, 72, 153, 0.06);
		color: var(--color-dim);
		font-size: 0.85rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		text-align: left;
	}
	.danger-btn:hover {
		background: rgba(236, 72, 153, 0.12);
		color: var(--color-pink);
	}
	.danger-btn.confirm {
		background: rgba(236, 72, 153, 0.2);
		color: var(--color-pink);
		border-color: var(--color-pink);
		font-weight: 600;
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
