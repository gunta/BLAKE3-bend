// b3bend against the BLAKE3s JavaScript has (@noble/hashes, hash-wasm,
// @napi-rs/blake-hash) and node:crypto's other hashes, in memory, one-shot,
// interleaved; medians in ms. Writes bend/bench/results/lang-<runtime>.json.
//   node bench.mjs     bun bench.mjs
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { blake3 as noble } from "@noble/hashes/blake3.js";
import { blake3 as hashWasm } from "hash-wasm";
import { blake3 as napiRs } from "@napi-rs/blake-hash";
import { blake3 } from "./index.js";

const runtime = typeof Bun !== "undefined" ? `bun ${Bun.version}` : `node ${process.versions.node}`;
const SIZES = [1 << 10, 64 << 10, 1 << 20, 16 << 20, 256 << 20, 1 << 30];
const OTHERS = ["sha256", "sha512", "sha1", "md5", "blake2b512", "blake2s256", "sha3-256"];
const data = new Uint8Array(1 << 30);
for (let i = 0; i < data.length; i += 1) data[i] = (Math.imul(i, 2654435761) >>> 13) & 255;

const sides = {
  b3bend: (b) => blake3(b),
  "@napi-rs/blake-hash": (b) => napiRs(b),
  "hash-wasm": (b) => hashWasm(b),
  "@noble/hashes": (b) => noble(b),
};
for (const a of OTHERS) {
  try {
    createHash(a).update(new Uint8Array(1)).digest();
    sides[`crypto ${a}`] = (b) => createHash(a).update(b).digest();
  } catch {}
}
const reps = (n) => (n <= 1 << 20 ? 30 : n <= 64 << 20 ? 9 : 3);
const hex = (x) => (typeof x === "string" ? x : Buffer.from(x).toString("hex")).slice(0, 16);
const rows = [];
for (const n of SIZES) {
  const b = data.subarray(0, n);
  const t = Object.fromEntries(Object.keys(sides).map((k) => [k, []]));
  const d = {};
  for (const [k, f] of Object.entries(sides)) d[k] = hex(await f(b));
  for (let r = 0; r < reps(n); r += 1) {
    for (const [k, f] of Object.entries(sides)) {
      if (k === "@noble/hashes" && n > 256 << 20 && r > 0) continue;
      const s = performance.now();
      await f(b);
      t[k].push(performance.now() - s);
    }
  }
  for (const k of Object.keys(sides)) {
    const v = t[k].sort((x, y) => x - y);
    rows.push({ impl: k, bytes: n, ms: v[v.length >> 1], digest: d[k] });
  }
}
const agree = SIZES.every((n) => ["b3bend", "@napi-rs/blake-hash", "hash-wasm", "@noble/hashes"]
  .every((k) => rows.find((r) => r.impl === k && r.bytes === n).digest === rows.find((r) => r.impl === "b3bend" && r.bytes === n).digest));
const impls = Object.keys(sides);
console.log(`${runtime}\n\n| bytes | ${impls.join(" | ")} |\n|---:|${"---:|".repeat(impls.length)}`);
for (const n of SIZES) {
  const size = n >= 1 << 30 ? `${n >> 30} GiB` : n >= 1 << 20 ? `${n >> 20} MiB` : `${n >> 10} KiB`;
  console.log(`| ${size} | ${impls.map((k) => `${rows.find((r) => r.impl === k && r.bytes === n).ms.toFixed(3)} ms`).join(" | ")} |`);
}
console.log(`\nBLAKE3 digests ${agree ? "agree" : "DIFFER"}`);
const name = runtime.split(" ")[0];
const out = new URL(`../bench/results/lang-${name}.json`, import.meta.url);
writeFileSync(out, JSON.stringify({ info: { runtime, digests_agree: agree }, rows }, null, 2) + "\n");
console.log(`wrote ${out.pathname}`);
