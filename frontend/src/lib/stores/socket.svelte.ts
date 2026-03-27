/**
 * Socket.IO reactive store — single connection shared across all components.
 * Uses Svelte 5 runes for fine-grained reactivity.
 */
import { base } from '$app/paths';
import { io, type Socket } from 'socket.io-client';

// Connection state
let socket: Socket | null = $state(null);
let connected = $state(false);

// Queues for calls made before connect()
let pendingListeners: Array<[string, (...args: any[]) => void]> = [];
let pendingEmits: Array<[string, unknown[]]> = [];

/** Connect to the Socket.IO server. Idempotent — safe to call multiple times. */
export function connect() {
  if (socket?.connected) return;

  socket = io({
    path: `${base}/socket.io/`,
    transports: ['websocket', 'polling'],
  });

  // Replay listeners registered before connect
  for (const [event, handler] of pendingListeners) {
    socket.on(event, handler);
  }
  pendingListeners = [];

  // Replay emits queued before connect
  for (const [event, args] of pendingEmits) {
    socket.emit(event, ...args);
  }
  pendingEmits = [];

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

/** Emit an event. Queued if called before connect(). */
export function emit(event: string, ...args: unknown[]) {
  if (socket) {
    socket.emit(event, ...args);
  } else {
    pendingEmits.push([event, args]);
  }
}

/** Emit a volatile event. Dropped if the connection is not currently ready. */
export function emitVolatile(event: string, ...args: unknown[]) {
  if (socket?.connected) {
    socket.volatile.emit(event, ...args);
  }
}

/** Register a listener (returns cleanup function). Queued if called before connect(). */
export function on(
  event: string,
  handler: (...args: any[]) => void,
): () => void {
  if (socket) {
    socket.on(event, handler);
  } else {
    pendingListeners.push([event, handler]);
  }
  return () => {
    socket?.off(event, handler);
    pendingListeners = pendingListeners.filter(
      ([e, h]) => e !== event || h !== handler,
    );
  };
}
