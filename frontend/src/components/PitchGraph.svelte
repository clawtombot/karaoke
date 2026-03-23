<script lang="ts">
	/**
	 * SingStar-style pitch graph — Canvas 2D rendering.
	 * Shows scrolling reference pitch bars + singer's real-time pitch dot.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { centsDifference, type PitchReading } from '$lib/audio/pitch-detector';

	interface PitchNote {
		t: number;
		hz: number;
		midi: number;
	}

	let {
		referenceNotes = [],
		singerPitch = null,
		currentTimeSec = 0,
		visible = true,
	}: {
		referenceNotes: PitchNote[];
		singerPitch: PitchReading | null;
		currentTimeSec: number;
		visible: boolean;
	} = $props();

	let canvas: HTMLCanvasElement;
	let animId: number | null = null;

	// Pitch display range (MIDI note numbers)
	const MIN_MIDI = 48; // C3
	const MAX_MIDI = 84; // C6
	const WINDOW_SECONDS = 6; // Total visible time window
	const CURSOR_X_RATIO = 0.3; // Singer dot position (30% from left)

	// Colors
	const REF_BAR_COLOR = 'rgba(124, 58, 237, 0.5)';
	const REF_BAR_BORDER = 'rgba(124, 58, 237, 0.8)';
	const GREEN = '#00ff88';
	const YELLOW = '#ffdd00';
	const RED = '#ff4444';
	const GRID_COLOR = 'rgba(255, 255, 255, 0.04)';

	function midiToY(midi: number, height: number): number {
		const clamped = Math.max(MIN_MIDI, Math.min(MAX_MIDI, midi));
		return height - ((clamped - MIN_MIDI) / (MAX_MIDI - MIN_MIDI)) * height;
	}

	function timeToX(t: number, current: number, width: number): number {
		const offset = t - current;
		return (offset / WINDOW_SECONDS) * width + width * CURSOR_X_RATIO;
	}

	function getPitchColor(singerHz: number, refHz: number): string {
		const cents = Math.abs(centsDifference(singerHz, refHz));
		if (cents < 50) return GREEN;
		if (cents < 150) return YELLOW;
		return RED;
	}

	function findNearestRef(time: number): PitchNote | null {
		let closest: PitchNote | null = null;
		let minDist = Infinity;
		for (const note of referenceNotes) {
			const dist = Math.abs(note.t - time);
			if (dist < minDist && dist < 0.2) {
				minDist = dist;
				closest = note;
			}
		}
		return closest;
	}

	function render() {
		if (!canvas || !visible) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const dpr = window.devicePixelRatio || 1;
		const rect = canvas.getBoundingClientRect();
		canvas.width = rect.width * dpr;
		canvas.height = rect.height * dpr;
		ctx.scale(dpr, dpr);

		const w = rect.width;
		const h = rect.height;

		// Clear
		ctx.clearRect(0, 0, w, h);

		// Subtle grid lines for pitch reference
		for (let midi = MIN_MIDI; midi <= MAX_MIDI; midi += 12) {
			const y = midiToY(midi, h);
			ctx.strokeStyle = GRID_COLOR;
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.moveTo(0, y);
			ctx.lineTo(w, y);
			ctx.stroke();
		}

		// Cursor line (where singer dot sits)
		const cursorX = w * CURSOR_X_RATIO;
		ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(cursorX, 0);
		ctx.lineTo(cursorX, h);
		ctx.stroke();

		// Draw reference pitch bars
		const visibleStart = currentTimeSec - WINDOW_SECONDS * CURSOR_X_RATIO;
		const visibleEnd = currentTimeSec + WINDOW_SECONDS * (1 - CURSOR_X_RATIO);

		for (let i = 0; i < referenceNotes.length; i++) {
			const note = referenceNotes[i];
			if (note.t < visibleStart || note.t > visibleEnd) continue;

			const x = timeToX(note.t, currentTimeSec, w);
			const y = midiToY(note.midi, h);

			// Find duration: time until next note or default 0.05s
			const nextNote = i + 1 < referenceNotes.length ? referenceNotes[i + 1] : null;
			const duration = nextNote ? Math.min(nextNote.t - note.t, 0.3) : 0.05;
			const barWidth = Math.max(2, (duration / WINDOW_SECONDS) * w);

			// Bar is brighter if near cursor (current time)
			const distFromCursor = Math.abs(note.t - currentTimeSec);
			const alpha = distFromCursor < 0.5 ? 0.7 : 0.4;

			ctx.fillStyle = REF_BAR_COLOR.replace('0.5', String(alpha));
			ctx.strokeStyle = REF_BAR_BORDER;
			ctx.lineWidth = 1;

			const barHeight = 6;
			ctx.beginPath();
			ctx.roundRect(x, y - barHeight / 2, barWidth, barHeight, 3);
			ctx.fill();
			ctx.stroke();
		}

		// Draw singer pitch dot
		if (singerPitch && singerPitch.hz > 0) {
			const singerMidi = 69 + 12 * Math.log2(singerPitch.hz / 440);
			const singerY = midiToY(singerMidi, h);

			// Color based on proximity to reference
			const nearestRef = findNearestRef(currentTimeSec);
			const dotColor = nearestRef ? getPitchColor(singerPitch.hz, nearestRef.hz) : '#ffffff';

			// Glow
			ctx.shadowColor = dotColor;
			ctx.shadowBlur = 12;

			// Dot
			ctx.fillStyle = dotColor;
			ctx.beginPath();
			ctx.arc(cursorX, singerY, 6, 0, Math.PI * 2);
			ctx.fill();

			// Reset shadow
			ctx.shadowBlur = 0;

			// Trail (last few positions — simple fade)
			ctx.globalAlpha = 0.3;
			ctx.fillStyle = dotColor;
			ctx.beginPath();
			ctx.arc(cursorX - 8, singerY, 4, 0, Math.PI * 2);
			ctx.fill();
			ctx.beginPath();
			ctx.arc(cursorX - 14, singerY, 2.5, 0, Math.PI * 2);
			ctx.fill();
			ctx.globalAlpha = 1;
		}
	}

	// Re-render on every prop change
	$effect(() => {
		// Touch reactive deps
		currentTimeSec;
		singerPitch;
		referenceNotes;
		visible;
		render();
	});

	onMount(() => {
		render();
	});
</script>

{#if visible}
	<div class="pitch-container">
		<canvas bind:this={canvas}></canvas>
	</div>
{/if}

<style>
	.pitch-container {
		position: absolute;
		top: 2%;
		left: 5%;
		right: 5%;
		height: 18%;
		z-index: 4;
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		background: rgba(13, 6, 24, 0.35);
		border: 1px solid rgba(124, 58, 237, 0.2);
		border-radius: 12px;
		overflow: hidden;
		pointer-events: none;
	}

	canvas {
		width: 100%;
		height: 100%;
		display: block;
	}
</style>
