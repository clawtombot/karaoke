<script lang="ts">
	import '../app.css';
	import { onMount, onDestroy } from 'svelte';
	import { connect, disconnect, on } from '$lib/stores/socket.svelte';
	import { update as updatePlayback, updateStemMix, fetchNowPlaying } from '$lib/stores/playback.svelte';

	let { children } = $props();

	onMount(() => {
		connect();

		// Listen for real-time updates from server
		const unsubs = [
			on('now_playing', (np: any) => updatePlayback(np)),
			on('stem_mix_update', (mix: any) => updateStemMix(mix)),
		];

		// Fetch initial state
		fetchNowPlaying();

		return () => unsubs.forEach((fn) => fn());
	});

	onDestroy(() => {
		disconnect();
	});
</script>

{@render children()}
