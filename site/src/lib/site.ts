/** Site-wide constants and URL helpers. */

export const REPO_URL = 'https://github.com/gunta/BLAKE3-bend';
export const REPO_BRANCH = 'master';
export const UPSTREAM_URL = 'https://github.com/BLAKE3-team/BLAKE3';
export const BEND_URL = 'https://bend-lang.com';

export const SITE_TITLE = 'BLAKE3 in Bend2';
export const SITE_DESCRIPTION =
  'A BLAKE3 hash and a byte-identical b3sum written in Bend2, raced against the official Rust/C BLAKE3: where it wins, where it ties, and the floors it hits.';

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
