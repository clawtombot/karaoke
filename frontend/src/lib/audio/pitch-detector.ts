/**
 * Real-time pitch detection from microphone using pitchy (McLeod Pitch Method).
 * Feeds the SingStar-style pitch graph with singer's current pitch.
 */
import { PitchDetector } from 'pitchy';

export interface PitchReading {
	hz: number;
	midi: number;
	clarity: number;
	timestamp: number;
}

let audioContext: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let detector: ReturnType<typeof PitchDetector.forFloat32Array> | null = null;
let inputBuffer: Float32Array | null = null;
let stream: MediaStream | null = null;
let animFrameId: number | null = null;
let onPitch: ((reading: PitchReading | null) => void) | null = null;

const CLARITY_THRESHOLD = 0.9;
const MIN_FREQUENCY = 60; // Hz — below this is noise
const MAX_FREQUENCY = 1500; // Hz — above this is unlikely vocal
const MIN_RMS = 0.02; // Volume gate — ignore signal below this energy level

// Vibrato smoothing — median of recent readings collapses 5-7 Hz oscillation
const SMOOTH_SIZE = 7; // ~117ms at 60fps
let hzBuffer: number[] = [];

function medianHz(raw: number): number {
	hzBuffer.push(raw);
	if (hzBuffer.length > SMOOTH_SIZE) hzBuffer.shift();
	if (hzBuffer.length < 3) return raw;
	const sorted = [...hzBuffer].sort((a, b) => a - b);
	return sorted[Math.floor(sorted.length / 2)];
}

/** List available audio input devices. */
export async function getAudioInputs(): Promise<MediaDeviceInfo[]> {
	// Need initial permission before labels appear
	try {
		const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
		tempStream.getTracks().forEach((t) => t.stop());
	} catch {
		// Permission denied — return empty
		return [];
	}

	const devices = await navigator.mediaDevices.enumerateDevices();
	return devices.filter((d) => d.kind === 'audioinput');
}

/** Start pitch detection from a specific audio input device. */
export async function start(
	callback: (reading: PitchReading | null) => void,
	deviceId?: string
) {
	stop(); // Clean up any existing session

	onPitch = callback;

	const constraints: MediaStreamConstraints = {
		audio: {
			deviceId: deviceId ? { exact: deviceId } : undefined,
			echoCancellation: false, // CRITICAL: disable for vocal input
			noiseSuppression: false,
			autoGainControl: false,
		},
	};

	try {
		stream = await navigator.mediaDevices.getUserMedia(constraints);
	} catch (e) {
		console.error('[pitch-detector] getUserMedia failed:', e);
		return;
	}

	audioContext = new AudioContext();
	const source = audioContext.createMediaStreamSource(stream);

	analyser = audioContext.createAnalyser();
	analyser.fftSize = 2048;
	source.connect(analyser);

	detector = PitchDetector.forFloat32Array(analyser.fftSize);
	inputBuffer = new Float32Array(detector.inputLength);

	// Start detection loop
	detect();
}

function detect() {
	if (!analyser || !detector || !inputBuffer || !audioContext) return;

	analyser.getFloatTimeDomainData(inputBuffer);

	// Volume gate — skip pitch detection when signal is too quiet (no one singing)
	let sum = 0;
	for (let i = 0; i < inputBuffer.length; i++) sum += inputBuffer[i] * inputBuffer[i];
	const rms = Math.sqrt(sum / inputBuffer.length);

	const [hz, clarity] = detector.findPitch(inputBuffer, audioContext.sampleRate);

	if (rms > MIN_RMS && clarity > CLARITY_THRESHOLD && hz > MIN_FREQUENCY && hz < MAX_FREQUENCY) {
		const smoothed = medianHz(hz);
		const midi = Math.round(69 + 12 * Math.log2(smoothed / 440));
		onPitch?.({
			hz: Math.round(smoothed * 100) / 100,
			midi,
			clarity: Math.round(clarity * 1000) / 1000,
			timestamp: audioContext.currentTime,
		});
	} else {
		onPitch?.(null); // No clear pitch detected
	}

	animFrameId = requestAnimationFrame(detect);
}

/** Stop pitch detection and release resources. */
export function stop() {
	if (animFrameId !== null) {
		cancelAnimationFrame(animFrameId);
		animFrameId = null;
	}

	if (stream) {
		stream.getTracks().forEach((t) => t.stop());
		stream = null;
	}

	if (audioContext) {
		audioContext.close();
		audioContext = null;
	}

	analyser = null;
	detector = null;
	inputBuffer = null;
	onPitch = null;
	hzBuffer = [];
}

/** Convert Hz to MIDI note number. */
export function hzToMidi(hz: number): number {
	return Math.round(69 + 12 * Math.log2(hz / 440));
}

/** Convert MIDI note number to note name. */
export function midiToNoteName(midi: number): string {
	const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
	const octave = Math.floor(midi / 12) - 1;
	const note = names[midi % 12];
	return `${note}${octave}`;
}

/** Calculate cents difference between two pitches (octave-agnostic). */
export function centsDifference(singerHz: number, referenceHz: number): number {
	if (singerHz <= 0 || referenceHz <= 0) return Infinity;
	// Octave-agnostic: compare within the same octave
	const ratio = singerHz / referenceHz;
	const octaveRatio = Math.pow(2, Math.round(Math.log2(ratio)));
	const adjustedRatio = ratio / octaveRatio;
	return 1200 * Math.log2(adjustedRatio);
}
