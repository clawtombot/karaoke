<script lang="ts">
	/**
	 * Root page — redirects to /remote (phone) or /splash (TV) based on screen size.
	 * For now, show a simple landing with links to both.
	 */
	import { getState } from '$lib/stores/playback.svelte';
	import { base } from '$app/paths';
	import { isConnected } from '$lib/stores/socket.svelte';

	const np = $derived(getState());
	const socketOk = $derived(isConnected());
</script>

<div class="relative z-10 flex min-h-screen items-center justify-center p-4">
	<div class="glass w-full max-w-md p-8 text-center">
		<h1 class="gradient-text mb-2 text-3xl font-bold" style="font-family: var(--font-display)">
			TommysKaraoke
		</h1>
		<p class="mb-6 text-sm" style="color: var(--color-dim)">
			{#if socketOk}
				<span style="color: var(--color-green)">&#9679;</span> Connected
			{:else}
				<span style="color: var(--color-pink)">&#9679;</span> Connecting...
			{/if}
		</p>

		{#if np.now_playing}
			<div class="glass-light mb-6 rounded-xl p-4 text-left">
				<div class="mb-1 text-xs font-semibold uppercase tracking-wider" style="color: var(--color-dim)">
					Now Playing
				</div>
				<div class="text-lg font-bold" style="color: var(--color-text)">{np.now_playing}</div>
				<div class="text-sm" style="color: var(--color-teal)">{np.now_playing_user}</div>
			</div>
		{/if}

		<div class="flex flex-col gap-3">
			<a
				href="{base}/remote"
				class="glow-purple block rounded-xl px-6 py-3 text-center font-semibold text-white"
				style="background: linear-gradient(135deg, var(--color-purple), var(--color-teal))"
			>
				Phone Remote
			</a>
			<a
				href="{base}/splash"
				class="glass-light block rounded-xl px-6 py-3 text-center font-semibold"
				style="color: var(--color-teal)"
			>
				TV Display
			</a>
			<a
				href="{base}/search"
				class="glass-light block rounded-xl px-6 py-3 text-center font-semibold"
				style="color: var(--color-dim)"
			>
				Search Songs
			</a>
			<a
				href="{base}/browse"
				class="glass-light block rounded-xl px-6 py-3 text-center font-semibold"
				style="color: var(--color-dim)"
			>
				Browse Library
			</a>
		</div>

		<div class="mt-4 flex justify-center">
			<a
				href="{base}/settings"
				class="flex items-center gap-2 text-xs font-semibold"
				style="color: var(--color-faint)"
			>
				&#9881; Settings
			</a>
		</div>
	</div>
</div>
