import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		port: 5173,
		proxy: {
			// Proxy API calls to the FastAPI backend
			'/api': {
				target: 'http://localhost:5555',
				changeOrigin: true,
			},
			// Proxy Socket.IO to the backend
			'/socket.io': {
				target: 'http://localhost:5555',
				ws: true,
				changeOrigin: true,
			},
			// Proxy media streams during development
			'/stream': 'http://localhost:5555',
			'/stems': 'http://localhost:5555',
			'/subtitle': 'http://localhost:5555',
			'/bg_music': 'http://localhost:5555',
			'/bg_playlist': 'http://localhost:5555',
			'/qrcode': 'http://localhost:5555',
			'/logo': 'http://localhost:5555',
			'/static': 'http://localhost:5555',
		},
	},
});
