---
name: migrate-to-turboblake-typescript
description: Move a TypeScript or JavaScript project (Node.js, Bun, Deno, Electron, browsers) from @noble/hashes/blake3, the blake3 npm package, hash-wasm or @napi-rs/blake-hash to turboblake, the drop-in that hashes BLAKE3 natively on every CPU core with a pure-JS fallback. Use when the user asks to speed up BLAKE3 in JS/TS or switch to turboblake.
---

# Migrate a TypeScript or JavaScript project to turboblake

`turboblake` is one npm package with two engines behind one API, and its own types:

- **native** (Node, Bun, Deno, Electron): a prebuilt Node-API addon over libturboblake,
  big inputs hashed on every core. Prebuilt for macOS, Linux (glibc and musl) and Windows,
  arm64 and x64; no install script, nothing compiles.
- **bend-js** (browsers, workers, anything else): BLAKE3 in plain JavaScript, chosen by
  bundlers through the `browser`/`worker` export conditions, or `turboblake/js`.

It exports both APIs JS code uses for BLAKE3, so most migrations are one import line.
Outputs are byte-for-byte BLAKE3.

## 1. Find what uses BLAKE3

```bash
grep -rnE "['\"](@noble/hashes/blake3(\.js)?|blake3|blake3-wasm|hash-wasm|@napi-rs/blake-hash)['\"]" \
  --include=*.ts --include=*.tsx --include=*.mts --include=*.cts --include=*.js --include=*.mjs --include=*.cjs \
  --exclude-dir=node_modules --exclude-dir=dist .
grep -nE '"(@noble/hashes|blake3|blake3-wasm|hash-wasm|@napi-rs/blake-hash)"' package.json
```

Only BLAKE3 call sites move. `@noble/hashes` and `hash-wasm` stay if the project uses them
for other hashes (sha256, argon2…).

## 2. Add the package

Use the project's package manager (look for `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`/
`bun.lockb`, `deno.json`, else npm):

```bash
npm install turboblake      # pnpm add / yarn add / bun add turboblake
deno add npm:turboblake
```

Remove `blake3`, `blake3-wasm` or `@napi-rs/blake-hash` from `package.json` once nothing
imports them.

## 3. Swap the imports

| was | now |
|---|---|
| `import { blake3 } from "@noble/hashes/blake3.js"` (or `/blake3`) | `import { blake3 } from "turboblake"` |
| `import { hash, keyedHash, deriveKey, createHash, createKeyed, createDeriveKey } from "blake3"` | same names `from "turboblake"` |
| `import { blake3 } from "hash-wasm"` (async, returns hex) | `blake3(data)` from turboblake: synchronous, returns bytes (see below) |
| `@napi-rs/blake-hash` `blake3(data)` (Buffer) | `hash(data)` from turboblake (Buffer) |

noble-style (`Uint8Array` out): `blake3(data)`, `blake3(data, { dkLen: 64, key })`,
`blake3(data, { context })`, `blake3.create(opts).update(a).update(b).digest()`,
`.xof(n)`, `.clone()`. `key` and `context` are `Uint8Array`s.

blake3-package-style (`Buffer` out): `hash(input, { length })`, `keyedHash(key, input)`,
`deriveKey(context, material)` (context is a string), `createHash().update(buf).digest("hex")`,
`.reader()` for extended output.

hash-wasm's `blake3(data, bits, key)` is async and returns hex: replace
`await blake3(data)` with `Buffer.from(blake3(data)).toString("hex")` (Node) or a hex helper
(browser), and `blake3(data, 512)` with `blake3(data, { dkLen: 64 })`. Check every caller
that awaited it still type-checks.

New, if useful: `await hashFiles(paths)` hashes many files at once (each a `Uint8Array` or an
`Error` with `errno` and `path`).

The package is ESM. CommonJS code can `require("turboblake")` on Node 20.19+ and 22.12+
(`require(esm)`); on older Node use `await import("turboblake")`.

## 4. Verify

```ts
import { blake3, backend } from "turboblake";
const hex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
console.assert(hex(blake3(new Uint8Array())) === "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262");
const input = Uint8Array.from({ length: 1024 }, (_, i) => i % 251);
console.assert(hex(blake3(input)) === "42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7");
console.log(backend); // "native" on Node/Bun/Deno, "bend-js" in browsers
```

Then the project's type check (`tsc --noEmit`) and tests. If `backend` is `"bend-js"` on a
server, the platform had no prebuilt addon: `node node_modules/turboblake/build.mjs`
builds one with clang.

## Know before you ship

- Bundling for Node (esbuild, webpack, Vite SSR): mark `turboblake` external so the native
  addon is loaded at run time, not bundled.
- Browser bundles get bend-js automatically; it is pure JS (no WebAssembly), every mode.
- On Windows the addon is the official BLAKE3 C (no engine yet): same results.
- It pays off on big inputs (hundreds of KiB and up); tiny hashes cost a native call.
- Rolling back: reinstall the old package and revert the import lines.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3.
Docs: https://gunta.github.io/turboblake/install/typescript/
