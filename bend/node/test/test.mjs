// turboblake against the official test vectors (every mode, extended output,
// seeks, update splits) through both of its faces, and against
// @noble/hashes on random inputs; then hashFiles. Run it with
// TURBOBLAKE_MIN=2048 too, so the engine takes every subtree.
//   node test/test.mjs     bun test/test.mjs
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { blake3 as noble } from "@noble/hashes/blake3.js";
import * as b from "../index.js";

const hex = (u) => Buffer.from(u).toString("hex");
const enc = new TextEncoder();
const vectors = JSON.parse(readFileSync(new URL("../../../test_vectors/test_vectors.json", import.meta.url)));
const pattern = (n) => Uint8Array.from({ length: n }, (_, i) => i % 251);
const key = enc.encode(vectors.key);
const ctx = enc.encode(vectors.context_string);
let checks = 0;

for (const c of vectors.cases) {
  const input = pattern(c.input_len);
  const full = c.hash.length / 2;
  for (const [mode, opts, want] of [
    ["hash", {}, c.hash],
    ["keyed", { key }, c.keyed_hash],
    ["derive", { context: ctx }, c.derive_key],
  ]) {
    assert.equal(hex(b.blake3(input, opts)), want.slice(0, 64), `${mode} ${c.input_len}`);
    assert.equal(hex(b.blake3(input, { ...opts, dkLen: full })), want, `${mode} xof ${c.input_len}`);
    for (const split of [1, 63, 1024, 1025, 4096]) {
      const h = b.blake3.create(opts);
      for (let i = 0; i < input.length; i += split) h.update(input.subarray(i, i + split));
      const x = h.clone();
      assert.equal(hex(h.digest()), want.slice(0, 64), `${mode} split ${split} ${c.input_len}`);
      assert.equal(hex(x.xof(7)) + hex(x.xof(full - 7)), want, `${mode} xof stream ${c.input_len}`);
      checks += 3;
    }
    const npm = mode === "hash" ? b.createHash() : mode === "keyed" ? b.createKeyed(Buffer.from(key))
      : b.createDeriveKey(vectors.context_string);
    npm.update(Buffer.from(input));
    assert.equal(npm.digest("hex", { length: full }), want, `npm ${mode} ${c.input_len}`);
    const r = npm.reader();
    r.read(5);
    assert.equal(r.read(full - 5).toString("hex"), want.slice(10), `npm reader ${mode}`);
    checks += 4;
  }
  assert.equal(b.hash(Buffer.from(input)).toString("hex"), c.hash.slice(0, 64));
  assert.equal(b.keyedHash(Buffer.from(key), Buffer.from(input)).toString("hex"), c.keyed_hash.slice(0, 64));
  assert.equal(b.deriveKey(vectors.context_string, Buffer.from(input)).toString("hex"), c.derive_key.slice(0, 64));
  checks += 3;
}
console.log(`${checks} official vector checks pass`);

// against @noble/hashes, random inputs to 64 MiB + 1
let seed = 7;
const rnd = () => (seed = (seed * 1103515245 + 12345) >>> 0);
const random = (n) => Uint8Array.from({ length: n }, () => rnd() & 255);
const big = random(64 << 20 | 1);
for (const n of [0, 1, 1023, 1024, 1025, 2049, 65536, 262143, 262145, 1 << 20, (3 << 20) + 77, 16 << 20, 64 << 20 | 1]) {
  const input = big.subarray(0, n);
  const k = random(32), x = random(40);
  for (const opts of [{}, { key: k }, { context: x }, { dkLen: 131 }]) {
    assert.equal(hex(b.blake3(input, opts)), hex(noble(input, opts)), `noble ${n} ${JSON.stringify(Object.keys(opts))}`);
    checks += 1;
  }
  const h = b.blake3.create(), m = noble.create();
  for (let i = 0; i < n; i += 99991) {
    h.update(input.subarray(i, i + 99991));
    m.update(input.subarray(i, i + 99991));
  }
  assert.equal(hex(h.xof(70)) + hex(h.xof(30)), hex(m.xof(100)), `noble xof ${n}`);
  checks += 1;
}
assert.throws(() => b.blake3(new Uint8Array(1), { key: new Uint8Array(31) }), RangeError);
console.log(`${checks} checks pass with @noble/hashes`);

// hashFiles
const dir = mkdtempSync(join(tmpdir(), "turboblake-"));
const files = [0, 1, 1025, 1 << 20, (5 << 20) + 3].map((n, i) => {
  const p = join(dir, `f${i}`);
  writeFileSync(p, big.subarray(0, n));
  return p;
});
const got = await b.hashFiles([...files, join(dir, "missing"), dir]);
files.forEach((p, i) => assert.equal(hex(got[i]), hex(noble(readFileSync(p))), p));
assert.equal(got[files.length].errno, 2);
assert.equal(got[files.length + 1].errno, 21);
console.log(`hashFiles: ${files.length} files and 2 errors as expected; all pass`);
