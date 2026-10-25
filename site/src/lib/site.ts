/** Site-wide constants and URL helpers. */

export const REPO_URL = 'https://github.com/gunta/BLAKE3-bend';
export const REPO_BRANCH = 'master';
export const UPSTREAM_URL = 'https://github.com/BLAKE3-team/BLAKE3';
export const BEND_URL = 'https://bend-lang.com';

/** The name, the crate and the command are one word. BRAND.md has the reasoning. */
export const SITE_NAME = 'b3bend';
export const SITE_TITLE = 'b3bend · BLAKE3, the SHA-256 replacement, bent for speed';
export const SITE_DESCRIPTION =
  'b3bend is BLAKE3, the fast SHA-256 replacement, written in Bend2: a byte-identical b3sum raced against the official Rust/C. Where it wins, where it ties, and the floors it hits.';
/** How to get it: the crate and the command share the name. */
export const INSTALL = 'cargo install b3bend';

/** A file in the repository on GitHub, e.g. blobUrl('adr/0002-….md'). */
export function blobUrl(path: string): string {
  return `${REPO_URL}/blob/${REPO_BRANCH}/${path.replace(/^\/+/, '')}`;
}

/** A directory in the repository on GitHub. */
export function treeUrl(path: string): string {
  return `${REPO_URL}/tree/${REPO_BRANCH}/${path.replace(/^\/+/, '')}`;
}

/**
 * An internal path under the configured `base` ("/BLAKE3-bend"), whether or not
 * BASE_URL carries a trailing slash. withBase('og.png') -> "/BLAKE3-bend/og.png".
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
