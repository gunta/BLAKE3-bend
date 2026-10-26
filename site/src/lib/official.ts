/**
 * What the BLAKE3 team says about BLAKE3, for the explainer sections, with
 * where they say it. Nothing here is measured by this project.
 */

export const BLAKE3_README = 'https://github.com/BLAKE3-team/BLAKE3#readme';
export const BLAKE3_PAPER = 'https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/blake3.pdf';

/**
 * The README's speed chart: one thread, 16 KiB input, AWS c5.metal (Cascade
 * Lake-SP 8275CL), MiB/s. MD5, SHA-1, SHA-2 and SHA-3 are OpenSSL's.
 * https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/benchmarks/bar_chart.py
 */
export const OFFICIAL_SPEED = {
  source: 'https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/benchmarks/bar_chart.py',
  setup: 'one thread, 16 KiB input, AWS c5.metal (2019)',
  unit: 'MiB/s',
  bars: [
    { name: 'BLAKE3', value: 6866 },
    { name: 'BLAKE2b', value: 1312 },
    { name: 'SHA-1', value: 1027 },
    { name: 'BLAKE2s', value: 876 },
    { name: 'MD5', value: 740 },
    { name: 'SHA-512', value: 720 },
    { name: 'SHA-256', value: 484 },
    { name: 'SHA3-256', value: 394 },
  ],
} as const;

/** BLAKE3 against the hashes people already use, row by row, from the README. */
export const COMPARISON = {
  columns: ['MD5', 'SHA-1', 'SHA-256', 'BLAKE3'] as const,
  rows: [
    { label: 'Secure against collisions', cells: ['Broken', 'Broken', 'Yes', 'Yes'] },
    { label: 'Secure against length extension', cells: ['No', 'No', 'No', 'Yes'] },
    { label: 'Splits one input across every core', cells: ['No', 'No', 'No', 'Yes'] },
    { label: 'Verified streaming of a part', cells: ['No', 'No', 'No', 'Yes'] },
    { label: 'Also a MAC, KDF and extendable output', cells: ['No', 'No', 'With HMAC, HKDF', 'Built in'] },
  ],
} as const;
