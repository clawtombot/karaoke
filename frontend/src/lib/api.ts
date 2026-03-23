import { base } from '$app/paths';

/** Prefix a path with the SvelteKit base path (handles proxy prefixes like /karaoke). */
export function api(path: string): string {
	return `${base}${path}`;
}
