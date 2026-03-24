<script lang="ts">
	/**
	 * SingStar-style pitch graph — pill-shaped note bars with progressive fill
	 * and particle bursts when the playhead crosses each note.
	 */
	import { onMount } from 'svelte';
	import { centsDifference, type PitchReading } from '$lib/audio/pitch-detector';

	interface PitchNote {
		t: number;
		hz: number;
		midi: number;
	}

	interface NoteSegment {
		startTime: number;
		endTime: number;
		midi: number;
		hz: number;
	}

	interface Particle {
		x: number;
		y: number;
		vx: number;
		vy: number;
		alpha: number;
		size: number;
	}

	let {
		referenceNotes = [],
		singerPitch = null,
		currentTimeSec = 0,
		visible = true,
		loading = false,
	}: {
		referenceNotes: PitchNote[];
		singerPitch: PitchReading | null;
		currentTimeSec: number;
		visible: boolean;
		loading: boolean;
	} = $props();

	let canvas: HTMLCanvasElement;

	// Pitch display range
	const PADDING_SEMITONES = 3;
	const FALLBACK_MIN = 48;
	const FALLBACK_MAX = 84;

	let minMidi = $derived.by(() => {
		if (referenceNotes.length === 0) return FALLBACK_MIN;
		let lo = Infinity;
		for (const n of referenceNotes) if (n.midi < lo) lo = n.midi;
		return Math.max(0, lo - PADDING_SEMITONES);
	});
	let maxMidi = $derived.by(() => {
		if (referenceNotes.length === 0) return FALLBACK_MAX;
		let hi = -Infinity;
		for (const n of referenceNotes) if (n.midi > hi) hi = n.midi;
		return Math.min(127, hi + PADDING_SEMITONES);
	});

	const WINDOW_SECONDS = 8;
	const CURSOR_X_RATIO = 0.3;
	const LABEL_WIDTH = 32;

	// Colors
	const NOTE_COLOR = '#ff69b4';
	const GREEN = '#00ff88';
	const YELLOW = '#ffdd00';
	const RED = '#ff4444';

	const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
	const BLACK_KEYS = new Set([1, 3, 6, 8, 10]);

	// Merge consecutive same-MIDI frames into note segments
	let segments: NoteSegment[] = $derived.by(() => {
		if (referenceNotes.length === 0) return [];
		const segs: NoteSegment[] = [];
		let cur: NoteSegment = {
			startTime: referenceNotes[0].t,
			endTime: referenceNotes[0].t,
			midi: referenceNotes[0].midi,
			hz: referenceNotes[0].hz,
		};
		for (let i = 1; i < referenceNotes.length; i++) {
			const note = referenceNotes[i];
			if (note.midi === cur.midi && note.t - cur.endTime < 0.08) {
				cur.endTime = note.t;
			} else {
				cur.endTime += 0.03;
				segs.push({ ...cur });
				cur = { startTime: note.t, endTime: note.t, midi: note.midi, hz: note.hz };
			}
		}
		cur.endTime += 0.03;
		segs.push({ ...cur });
		return segs;
	});

	// Particle system
	let particles: Particle[] = [];
	let hitSegments = new Set<number>();
	let prevRefNotes: PitchNote[] = [];
	let lastTime = 0;

	function spawnParticles(x: number, y: number, barH: number) {
		const cy = y + barH / 2;
		for (let i = 0; i < 14; i++) {
			const angle = Math.random() * Math.PI * 2;
			const speed = 25 + Math.random() * 90;
			particles.push({
				x: x + (Math.random() - 0.5) * 8,
				y: cy + (Math.random() - 0.5) * barH * 0.6,
				vx: Math.cos(angle) * speed,
				vy: Math.sin(angle) * speed - 15,
				alpha: 0.7 + Math.random() * 0.3,
				size: 1.5 + Math.random() * 3,
			});
		}
	}

	function noteRowHeight(h: number): number {
		return h / (maxMidi - minMidi);
	}

	function midiToY(midi: number, h: number): number {
		const clamped = Math.max(minMidi, Math.min(maxMidi, midi));
		return h - ((clamped - minMidi + 0.5) / (maxMidi - minMidi)) * h;
	}

	function midiToRowTop(midi: number, h: number): number {
		const clamped = Math.max(minMidi, Math.min(maxMidi, midi));
		return h - ((clamped - minMidi + 1) / (maxMidi - minMidi)) * h;
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

	/** Draw a pill-shaped bar with a knob at the leading (left) edge. */
	function drawPill(
		ctx: CanvasRenderingContext2D,
		x: number, y: number, w: number, h: number,
		filled: boolean
	) {
		const r = h / 2;
		const knobR = r * 1.3;

		if (filled) {
			ctx.fillStyle = NOTE_COLOR;
			ctx.beginPath();
			ctx.roundRect(x, y, w, h, r);
			ctx.fill();
			ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
			ctx.lineWidth = 1.5;
			ctx.stroke();

			// Knob at left edge
			ctx.beginPath();
			ctx.arc(x + r, y + r, knobR, 0, Math.PI * 2);
			ctx.fillStyle = NOTE_COLOR;
			ctx.fill();
			ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
			ctx.lineWidth = 1.5;
			ctx.stroke();
		} else {
			// Outlined pill with subtle fill
			ctx.fillStyle = 'rgba(255, 105, 180, 0.06)';
			ctx.strokeStyle = 'rgba(255, 105, 180, 0.3)';
			ctx.lineWidth = 1.5;
			ctx.beginPath();
			ctx.roundRect(x, y, w, h, r);
			ctx.fill();
			ctx.stroke();

			// Outlined knob
			ctx.beginPath();
			ctx.arc(x + r, y + r, knobR, 0, Math.PI * 2);
			ctx.fill();
			ctx.stroke();
		}
	}

	function render() {
		if (!canvas || !visible) return;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		// Reset on song change
		if (referenceNotes !== prevRefNotes) {
			prevRefNotes = referenceNotes;
			particles = [];
			hitSegments = new Set();
		}

		// dt for particle physics
		const rawDt = currentTimeSec - lastTime;
		const dt = rawDt > 0 && rawDt < 0.1 ? rawDt : 0;
		lastTime = currentTimeSec;

		// Reset on backward seek
		if (rawDt < -0.5) {
			hitSegments = new Set();
			particles = [];
		}

		const dpr = window.devicePixelRatio || 1;
		const rect = canvas.getBoundingClientRect();
		canvas.width = rect.width * dpr;
		canvas.height = rect.height * dpr;
		ctx.scale(dpr, dpr);

		const w = rect.width;
		const h = rect.height;
		const rowH = noteRowHeight(h);
		const graphX = LABEL_WIDTH;
		const graphW = w - LABEL_WIDTH;
		const cursorX = graphX + graphW * CURSOR_X_RATIO;

		ctx.clearRect(0, 0, w, h);

		// ── Background: subtle horizontal grid lines ──
		for (let midi = minMidi; midi < maxMidi; midi++) {
			const top = midiToRowTop(midi, h);
			ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
			ctx.lineWidth = 0.5;
			ctx.beginPath();
			ctx.moveTo(graphX, top + rowH);
			ctx.lineTo(w, top + rowH);
			ctx.stroke();
		}

		// ── Note labels ──
		ctx.fillStyle = 'rgba(13, 6, 24, 0.5)';
		ctx.fillRect(0, 0, LABEL_WIDTH, h);
		for (let midi = minMidi; midi < maxMidi; midi++) {
			const pc = midi % 12;
			if (BLACK_KEYS.has(pc)) continue;
			const top = midiToRowTop(midi, h);
			ctx.fillStyle = pc === 0 ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.25)';
			ctx.font = `${Math.max(8, Math.min(12, rowH * 0.65))}px monospace`;
			ctx.textAlign = 'right';
			ctx.textBaseline = 'middle';
			ctx.fillText(`${NOTE_NAMES[pc]}${Math.floor(midi / 12) - 1}`, LABEL_WIDTH - 4, top + rowH / 2);
		}

		// ── Note segments (pill-shaped bars) ──
		const visStart = currentTimeSec - WINDOW_SECONDS * CURSOR_X_RATIO;
		const visEnd = currentTimeSec + WINDOW_SECONDS * (1 - CURSOR_X_RATIO);
		const barH = Math.max(8, rowH * 0.7);

		for (let i = 0; i < segments.length; i++) {
			const seg = segments[i];
			if (seg.endTime < visStart || seg.startTime > visEnd) continue;

			const x1 = graphX + ((seg.startTime - currentTimeSec) / WINDOW_SECONDS) * graphW + graphW * CURSOR_X_RATIO;
			const x2 = graphX + ((seg.endTime - currentTimeSec) / WINDOW_SECONDS) * graphW + graphW * CURSOR_X_RATIO;
			const top = midiToRowTop(seg.midi, h);
			const barY = top + (rowH - barH) / 2;
			const barW = Math.max(barH, x2 - x1);

			const isPast = seg.endTime <= currentTimeSec;
			const isCrossing = seg.startTime <= currentTimeSec && seg.endTime > currentTimeSec;

			if (isPast) {
				drawPill(ctx, x1, barY, barW, barH, true);
			} else if (isCrossing) {
				// Progressive fill: outlined bar as base, clip-fill the past portion
				drawPill(ctx, x1, barY, barW, barH, false);
				ctx.save();
				ctx.beginPath();
				ctx.rect(0, 0, cursorX, h);
				ctx.clip();
				drawPill(ctx, x1, barY, barW, barH, true);
				ctx.restore();

				// Spawn particles on first crossing
				if (!hitSegments.has(i)) {
					hitSegments.add(i);
					spawnParticles(cursorX, barY, barH);
				}
			} else {
				drawPill(ctx, x1, barY, barW, barH, false);
			}
		}

		// ── Update and draw particles ──
		if (dt > 0) {
			for (let i = particles.length - 1; i >= 0; i--) {
				const p = particles[i];
				p.x += p.vx * dt;
				p.y += p.vy * dt;
				p.vy += 40 * dt; // gentle gravity
				p.alpha -= dt * 2.2;
				if (p.alpha <= 0) particles.splice(i, 1);
			}
		}
		for (const p of particles) {
			ctx.globalAlpha = Math.max(0, p.alpha);
			ctx.shadowColor = NOTE_COLOR;
			ctx.shadowBlur = 8;
			ctx.fillStyle = p.size > 2.5 ? '#fff' : NOTE_COLOR;
			ctx.beginPath();
			ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
			ctx.fill();
		}
		ctx.globalAlpha = 1;
		ctx.shadowBlur = 0;

		// ── Playhead ──
		ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(cursorX, 0);
		ctx.lineTo(cursorX, h);
		ctx.stroke();

		ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
		ctx.beginPath();
		ctx.moveTo(cursorX, 0);
		ctx.lineTo(cursorX - 4, 6);
		ctx.lineTo(cursorX + 4, 6);
		ctx.closePath();
		ctx.fill();

		// ── Singer pitch dot ──
		if (singerPitch && singerPitch.hz > 0) {
			const singerMidi = 69 + 12 * Math.log2(singerPitch.hz / 440);
			const singerY = midiToY(singerMidi, h);
			const nearestRef = findNearestRef(currentTimeSec);
			const dotColor = nearestRef ? getPitchColor(singerPitch.hz, nearestRef.hz) : '#ffffff';

			// Outer glow
			ctx.shadowColor = dotColor;
			ctx.shadowBlur = 14;
			ctx.fillStyle = dotColor;
			ctx.beginPath();
			ctx.arc(cursorX, singerY, 7, 0, Math.PI * 2);
			ctx.fill();

			// White core
			ctx.fillStyle = '#ffffff';
			ctx.beginPath();
			ctx.arc(cursorX, singerY, 3, 0, Math.PI * 2);
			ctx.fill();
			ctx.shadowBlur = 0;

			// Trail
			ctx.globalAlpha = 0.25;
			ctx.fillStyle = dotColor;
			ctx.beginPath();
			ctx.arc(cursorX - 10, singerY, 4.5, 0, Math.PI * 2);
			ctx.fill();
			ctx.beginPath();
			ctx.arc(cursorX - 18, singerY, 2.5, 0, Math.PI * 2);
			ctx.fill();
			ctx.globalAlpha = 1;
		}
	}

	$effect(() => {
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
		{#if loading}
			<div class="pitch-loading">
				<div class="pitch-loading-bar"></div>
				<span>Preparing pitch graph...</span>
			</div>
		{/if}
	</div>
{/if}

<style>
	.pitch-container {
		position: absolute;
		top: 2%;
		left: 3%;
		right: 3%;
		height: 25%;
		z-index: 4;
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		background: rgba(13, 6, 24, 0.35);
		border: 1px solid rgba(255, 105, 180, 0.15);
		border-radius: 14px;
		overflow: hidden;
		pointer-events: none;
	}

	canvas {
		width: 100%;
		height: 100%;
		display: block;
	}

	.pitch-loading {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 8px;
		background: rgba(13, 6, 24, 0.6);
	}

	.pitch-loading span {
		font: 11px/1 'Inter', sans-serif;
		color: rgba(255, 255, 255, 0.4);
		letter-spacing: 0.05em;
	}

	.pitch-loading-bar {
		width: 120px;
		height: 3px;
		border-radius: 2px;
		background: rgba(255, 255, 255, 0.08);
		overflow: hidden;
		position: relative;
	}

	.pitch-loading-bar::after {
		content: '';
		position: absolute;
		top: 0;
		left: -40%;
		width: 40%;
		height: 100%;
		border-radius: 2px;
		background: linear-gradient(90deg, transparent, rgba(255, 105, 180, 0.6), transparent);
		animation: shimmer 1.5s ease-in-out infinite;
	}

	@keyframes shimmer {
		0% { left: -40%; }
		100% { left: 100%; }
	}
</style>
