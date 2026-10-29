# turboblake (Node, Bun, Deno, browsers)

BLAKE3 for JavaScript, two engines behind one API:

- **native** (Node, Bun, Deno): a Node-API addon over libturboblake, the
  official BLAKE3 C library whose big inputs are hashed on every core by a
  [Bend2](https://bend-lang.com) engine;
- **bend-js** (browsers, workers, or a machine with no C compiler): BLAKE3
  as Bend wrote it, emitted to JavaScript by Bend2's own JS target
  (`js/blake3.mjs`, from `bend/js/blake3.bend`), every compression in
  Bend's code.

Bundlers pick bend-js through the `browser` and `worker` export conditions;
`import ... from "turboblake/js"` asks for it anywhere; `backend` says which
runs.

```bash
npm install turboblake
```

The package carries its native addon prebuilt for macOS (arm64, x64), Linux
(glibc and musl, arm64 and x64) and Windows (x64, arm64), and loads the one
for the machine it runs on: nothing compiles, and there is no install
script. The x64 addons take AVX2 where the CPU has it and run on any x64
CPU. On Windows the addon is the official BLAKE3 C (no engine there yet),
and it finds Node-API in whatever runs it, so one addon serves Node, Bun,
Deno and Electron. On any other platform turboblake runs on Bend's
JavaScript; `node build.mjs` inside the installed package builds an addon
for it (clang), and there it also tunes one for your CPU.

It is a drop-in for the two APIs JavaScript code uses for BLAKE3:

```js
// was: import { blake3 } from "@noble/hashes/blake3.js";
import { blake3 } from "turboblake";

blake3(data);                                   // Uint8Array(32)
blake3(data, { dkLen: 64, key });               // keyed, extended output
blake3.create({ context }).update(a).update(b).digest();
```

```js
// was: import { hash, createHash } from "blake3";  (the npm package no longer installs)
import { hash, keyedHash, deriveKey, createHash } from "turboblake";

hash("hello").toString("hex");
createHash().update(buf).digest("hex", { length: 64 });
```

and `await hashFiles(paths)` hashes many files at once, as the `turboblake`
command does: each a `Uint8Array`, or an `Error` with its `errno`.

Installing builds the addon from source (needs clang; `CC` picks another);
without one the install still succeeds and runs on bend-js.
Against the alternatives on an Apple M5 Pro, one-shot, 1 GiB in memory:
turboblake 38 ms, @napi-rs/blake-hash (native, one thread) 482 ms, hash-wasm
964 ms, @noble/hashes 10.9 s (3.1 s on Bun); node:crypto's sha256 335 ms. `node bench.mjs` or `bun bench.mjs` re-runs it;
`node test/test.mjs` (and `TURBOBLAKE_JS=1 node test/test.mjs` for bend-js)
checks the official vectors in every mode and @noble/hashes on random
inputs; `test/browser.html` (served by `test/serve.mjs`) checks bend-js in
a browser.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
