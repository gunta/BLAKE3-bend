// Checks src/lib/blake3.ts against the official test vectors: `pnpm test`.
// Each case hashes `len` bytes of the pattern i % 251; the first 32 bytes of
// the vector's extended output are the default hash.
import { readFileSync } from 'node:fs';
import { blake3, toHex } from '../src/lib/blake3.ts';

const vectors = JSON.parse(readFileSync(new URL('../../test_vectors/test_vectors.json', import.meta.url), 'utf8')) as {
  cases: { input_len: number; hash: string }[];
};

let failed = 0;
for (const { input_len, hash } of vectors.cases) {
  const input = Uint8Array.from({ length: input_len }, (_, i) => i % 251);
  const got = toHex(blake3(input));
  const want = hash.slice(0, 64);
  if (got !== want) {
    failed++;
    console.error(`len ${input_len}: got ${got}, want ${want}`);
  }
}
console.log(`${vectors.cases.length - failed}/${vectors.cases.length} test vectors match`);
process.exit(failed ? 1 : 0);
