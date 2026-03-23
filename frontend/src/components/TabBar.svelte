<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';

	const tabs = [
		{ href: '/remote', icon: 'ti ti-home-2', label: 'Home' },
		{ href: '/search', icon: 'ti ti-search', label: 'Search' },
		{ href: '/browse', icon: 'ti ti-music', label: 'Browse' },
		{ href: '/queue', icon: 'ti ti-list-numbers', label: 'Queue' },
	];

	function isActive(href: string): boolean {
		const path = page.url?.pathname ?? '';
		return path === `${base}${href}` || path === `${base}${href}/`;
	}
</script>

<nav class="pill-bar">
	{#each tabs as tab}
		<a href="{base}{tab.href}" class="pill-tab" class:active={isActive(tab.href)}>
			<i class="{tab.icon}"></i>
			<span>{tab.label}</span>
		</a>
	{/each}
</nav>

<style>
	.pill-bar {
		position: fixed;
		bottom: calc(12px + env(safe-area-inset-bottom, 0px));
		left: 50%;
		transform: translateX(-50%);
		z-index: 50;
		display: flex;
		gap: 4px;
		padding: 6px 8px;
		border-radius: 28px;
		background: rgba(18, 12, 36, 0.65);
		backdrop-filter: blur(24px) saturate(1.6);
		-webkit-backdrop-filter: blur(24px) saturate(1.6);
		border: 1px solid rgba(255, 255, 255, 0.08);
		box-shadow:
			0 8px 32px rgba(0, 0, 0, 0.4),
			inset 0 1px 0 rgba(255, 255, 255, 0.05);
	}

	.pill-tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1px;
		padding: 6px 16px;
		border-radius: 22px;
		color: rgba(255, 255, 255, 0.4);
		text-decoration: none;
		font-size: 0.55rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		transition: all 0.2s ease;
	}
	.pill-tab i {
		font-size: 1.15rem;
		transition: transform 0.2s ease;
	}
	.pill-tab:hover {
		color: rgba(255, 255, 255, 0.7);
		background: rgba(255, 255, 255, 0.06);
	}
	.pill-tab.active {
		color: var(--color-teal, #00d2ff);
		background: rgba(0, 210, 255, 0.1);
	}
	.pill-tab.active i {
		transform: scale(1.1);
	}
</style>
