/** Site-wide constants and URL helpers. */
import cargoToml from '../../../bend/crate/Cargo.toml?raw';

export const REPO_URL = 'https://github.com/gunta/turboblake';
export const REPO_BRANCH = 'master';
export const UPSTREAM_URL = 'https://github.com/BLAKE3-team/BLAKE3';
export const BEND_URL = 'https://bend-lang.com';

/** The name, the crate and the command are one word. BRAND.md has the reasoning. */
export const SITE_NAME = 'turboblake';
export const SITE_TITLE = 'turboblake · BLAKE3, turbocharged';
export const SITE_DESCRIPTION =
  'turboblake is BLAKE3, the SHA-256 replacement, turbocharged: a drop-in b3sum with a Bend2 engine, raced against the official Rust/C. Where it wins, where it ties, and the floors it hits.';
/** How to get it. Homebrew first: prebuilt, no Rust needed. The crate and the command share the name. */
export const INSTALLS = [
  { id: 'brew', label: 'Homebrew', command: 'brew install gunta/tap/turboblake', note: 'macOS and Linux, prebuilt' },
  { id: 'cargo', label: 'Cargo', command: 'cargo install turboblake', note: 'from source, tuned for your CPU' },
] as const;
export const INSTALL = INSTALLS[0].command;
export const RELEASES_URL = `${REPO_URL}/releases`;

/** A file in the repository on GitHub, e.g. blobUrl('adr/0002-….md'). */
export function blobUrl(path: string): string {
  return `${REPO_URL}/blob/${REPO_BRANCH}/${path.replace(/^\/+/, '')}`;
}

/** A directory in the repository on GitHub. */
export function treeUrl(path: string): string {
  return `${REPO_URL}/tree/${REPO_BRANCH}/${path.replace(/^\/+/, '')}`;
}

/**
 * An internal path under the configured `base` ("/turboblake"), whether or not
 * BASE_URL carries a trailing slash. withBase('og.png') -> "/turboblake/og.png".
 */
export function withBase(path = ''): string {
  const base = import.meta.env.BASE_URL.replace(/\/+$/, '');
  const rest = path.replace(/^\/+/, '');
  return rest ? `${base}/${rest}` : `${base}/`;
}

/** Absolute URL for meta tags (canonical, Open Graph). */
export function absoluteUrl(path: string, site: URL | undefined): string {
  return new URL(withBase(path), site ?? 'https://gunta.github.io').href;
}

/** The commit the site was built from, when GitHub Actions provides it. */
export function buildCommit(): string | undefined {
  const sha = process.env['GITHUB_SHA'];
  return sha && /^[0-9a-f]{7,40}$/i.test(sha) ? sha : undefined;
}

/** The CLI's version, read from its Cargo.toml so the page and the release agree. */
export const CLI_VERSION = /^version\s*=\s*"([^"]+)"/m.exec(cargoToml)?.[1] ?? '';
