/**
 * Socket.IO reactive store — single connection shared across all components.
 * Uses Svelte 5 runes for fine-grained reactivity.
 */
import { base } from '$app/paths';
import { io, type Socket } from 'socket.io-client';

// Connection state
let socket: Socket | null = $state(null);
let connected = $state(false);

/** Connect to the Socket.IO server. Idempotent — safe to call multiple times. */
export function connect() {
	if (socket?.connected) return;

	socket = io({
		path: `${base}/socket.io/`,
		transports: ['websocket', 'polling'],
	});

	socket.on('connect', () => {
		connected = true;
		console.log('[socket] connected', socket?.id);
	});

	socket.on('disconnect', (reason) => {
		connected = false;
		console.warn('[socket] disconnected:', reason);
	});

	socket.on('connect_error', (err) => {
		console.error('[socket] connection error:', err.message);
	});
}

/** Disconnect and clean up. */
export function disconnect() {
	socket?.disconnect();
	socket = null;
	connected = false;
}

/** Get the raw socket for event listening in components. */
export function getSocket(): Socket | null {
	return socket;
}

/** Reactive connected state for UI binding. */
export function isConnected(): boolean {
	return connected;
}

/** Emit an event. */
export function emit(event: string, ...args: unknown[]) {
	socket?.emit(event, ...args);
}

/** Register a listener (returns cleanup function). */
export function on(event: string, handler: (...args: unknown[]) => void): () => void {
	socket?.on(event, handler);
	return () => {
		socket?.off(event, handler);
	};
}
