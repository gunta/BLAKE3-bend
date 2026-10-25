/**
 * BLAKE3 in TypeScript, for the hero's "hash anything" box: a port of
 * reference_impl/reference_impl.rs (default hash mode, 32-byte output).
 * Small inputs only; it is the page's toy, not one of the benchmarked sides.
 * scripts/check-blake3.ts (`pnpm test`) checks it against test_vectors/test_vectors.json.
 */

const IV = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
const PERM = [2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8];

const CHUNK_START = 1;
const CHUNK_END = 2;
const PARENT = 4;
const ROOT = 8;

const BLOCK_LEN = 64;
const CHUNK_LEN = 1024;

const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));

function g(s: Uint32Array, a: number, b: number, c: number, d: number, mx: number, my: number): void {
  s[a] = (s[a]! + s[b]! + mx) | 0;
  s[d] = rotr(s[d]! ^ s[a]!, 16);
  s[c] = (s[c]! + s[d]!) | 0;
  s[b] = rotr(s[b]! ^ s[c]!, 12);
  s[a] = (s[a]! + s[b]! + my) | 0;
  s[d] = rotr(s[d]! ^ s[a]!, 8);
  s[c] = (s[c]! + s[d]!) | 0;
  s[b] = rotr(s[b]! ^ s[c]!, 7);
}

/** The compression function; returns the full 16-word state. */
function compress(cv: Uint32Array, block: Uint32Array, counter: number, blockLen: number, flags: number): Uint32Array {
  const s = new Uint32Array(16);
  s.set(cv, 0);
  s.set(IV.subarray(0, 4), 8);
  s[12] = counter >>> 0;
  s[13] = Math.floor(counter / 0x100000000) >>> 0;
  s[14] = blockLen;
  s[15] = flags;
  let m = Uint32Array.from(block);
  for (let round = 0; round < 7; round++) {
    g(s, 0, 4, 8, 12, m[0]!, m[1]!);
    g(s, 1, 5, 9, 13, m[2]!, m[3]!);
    g(s, 2, 6, 10, 14, m[4]!, m[5]!);
    g(s, 3, 7, 11, 15, m[6]!, m[7]!);
    g(s, 0, 5, 10, 15, m[8]!, m[9]!);
    g(s, 1, 6, 11, 12, m[10]!, m[11]!);
    g(s, 2, 7, 8, 13, m[12]!, m[13]!);
    g(s, 3, 4, 9, 14, m[14]!, m[15]!);
    if (round < 6) m = Uint32Array.from(PERM, (i) => m[i]!);
  }
  for (let i = 0; i < 8; i++) {
    s[i] = s[i]! ^ s[i + 8]!;
    s[i + 8] = s[i + 8]! ^ cv[i]!;
  }
  return s;
}

/** Little-endian words of a block, zero-padded to 64 bytes. */
function words(bytes: Uint8Array, start: number, len: number): Uint32Array {
  const w = new Uint32Array(16);
  for (let i = 0; i < len; i++) w[i >> 2] = w[i >> 2]! | (bytes[start + i]! << (8 * (i & 3)));
  return w;
}

interface Output {
  cv: Uint32Array;
  block: Uint32Array;
  counter: number;
  blockLen: number;
  flags: number;
}

function chainingValue(o: Output): Uint32Array {
  return compress(o.cv, o.block, o.counter, o.blockLen, o.flags).slice(0, 8);
}

/** Everything but the final compression of one chunk, so the caller can add ROOT. */
function chunkOutput(input: Uint8Array, start: number, end: number, counter: number): Output {
  let cv: Uint32Array = IV;
  const blocks = Math.max(1, Math.ceil((end - start) / BLOCK_LEN));
  for (let b = 0; b < blocks - 1; b++) {
    const flags = b === 0 ? CHUNK_START : 0;
    cv = compress(cv, words(input, start + b * BLOCK_LEN, BLOCK_LEN), counter, BLOCK_LEN, flags).slice(0, 8);
  }
  const at = start + (blocks - 1) * BLOCK_LEN;
  const len = end - at;
  return { cv, block: words(input, at, len), counter, blockLen: len, flags: (blocks === 1 ? CHUNK_START : 0) | CHUNK_END };
}

function parentOutput(left: Uint32Array, right: Uint32Array): Output {
  const block = new Uint32Array(16);
  block.set(left, 0);
  block.set(right, 8);
  return { cv: IV, block, counter: 0, blockLen: BLOCK_LEN, flags: PARENT };
}

/** BLAKE3 of `input`, 32 bytes. */
export function blake3(input: Uint8Array): Uint8Array {
  const chunks = Math.max(1, Math.ceil(input.length / CHUNK_LEN));
  // The tree is left-full: merge completed subtrees as the chunk count allows.
  const stack: Uint32Array[] = [];
  let out = chunkOutput(input, 0, Math.min(input.length, CHUNK_LEN), 0);
  for (let c = 1; c < chunks; c++) {
    let cv = chainingValue(out);
    let total = c;
    while ((total & 1) === 0) {
      cv = chainingValue(parentOutput(stack.pop()!, cv));
      total >>= 1;
    }
    stack.push(cv);
    out = chunkOutput(input, c * CHUNK_LEN, Math.min(input.length, (c + 1) * CHUNK_LEN), c);
  }
  while (stack.length) out = parentOutput(stack.pop()!, chainingValue(out));
  const s = compress(out.cv, out.block, out.counter, out.blockLen, out.flags | ROOT);
  const bytes = new Uint8Array(32);
  for (let i = 0; i < 32; i++) bytes[i] = (s[i >> 2]! >>> (8 * (i & 3))) & 0xff;
  return bytes;
}

export function toHex(bytes: Uint8Array): string {
  let hex = '';
  for (const b of bytes) hex += b.toString(16).padStart(2, '0');
  return hex;
}

/** BLAKE3 of a string's UTF-8 bytes, as `printf '%s' "$text" | b3sum` prints it. */
export function blake3Hex(text: string): string {
  return toHex(blake3(new TextEncoder().encode(text)));
}
