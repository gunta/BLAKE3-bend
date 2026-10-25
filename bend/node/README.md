# b3bend (Node, Bun, Deno)

BLAKE3 for JavaScript runtimes, as a native Node-API addon over
libblake3-bend: the official BLAKE3 C library whose big inputs are hashed on
every core by a [Bend2](https://bend-lang.com) engine. One addon serves
Node, Bun and Deno.

```bash
npm install b3bend
```

It is a drop-in for the two APIs JavaScript code uses for BLAKE3:

```js
// was: import { blake3 } from "@noble/hashes/blake3.js";
import { blake3 } from "b3bend";

blake3(data);                                   // Uint8Array(32)
blake3(data, { dkLen: 64, key });               // keyed, extended output
blake3.create({ context }).update(a).update(b).digest();
```

```js
// was: import { hash, createHash } from "blake3";  (the npm package no longer installs)
import { hash, keyedHash, deriveKey, createHash } from "b3bend";

hash("hello").toString("hex");
createHash().update(buf).digest("hex", { length: 64 });
```

and `await hashFiles(paths)` hashes many files at once, as the `b3bend`
command does: each a `Uint8Array`, or an `Error` with its `errno`.

Installing builds the addon from source (needs clang; `CC` picks another).
Against the alternatives on an Apple M5 Pro, one-shot, 1 GiB in memory:
b3bend 36 ms, @napi-rs/blake-hash (native, one thread) 445 ms, hash-wasm
975 ms, @noble/hashes 9.4 s on Node and 3.0 s on Bun; node:crypto's sha256
343 ms. `node bench.mjs` or `bun bench.mjs` re-runs it;
`node test/test.mjs` checks the official vectors in every mode and
@noble/hashes on random inputs.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
