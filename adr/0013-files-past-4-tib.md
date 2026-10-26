# ADR 0013: Files past 4 TiB: the chunk counter's high word

Date: 2026-10-26
Status: accepted

## Context

BLAKE3 numbers its chunks with a 64-bit counter: the compression function
takes it as two words, t0 and t1 (state words 12 and 13), and an input may
be up to 2^64 bytes. Bend2 has no U64, and since v1 every tree passed only
the low word (`cb`, `t`, `ctr`) with t1 = 0 in every compression. ADR 0004
noted the consequence, "chunk counters are U32, so files go to 4 TiB", and
the loader enforced it: a file of 2^32 chunks (4 TiB) or more failed with
EFBIG. So `b3sum` and turboblake printed `File too large` and exited 1 on a
file the official `b3sum` hashes, and the library engine (libblake3-bend,
blake3-bend, every binding) handed subtrees past 2^32 chunks back to the C
or Rust SIMD loop.

4 TiB is no longer exotic: disk images, backups and dataset shards reach it.
A drop-in for `b3sum` must hash whatever it hashes.

## Decision: a span carries its counter's high word

- Every def of `blake3.bend` that takes a chunk counter takes `hi`, the
  counter's high word, beside it: the spans' entry points (`hash.at`,
  `hash1.at`, `hash8.at.k`, `hash.ob.at`, `hash.at.k`), every tree (CPU,
  GPU, outboard, keyed, scalar), every leaf (`leaf32`, `leaf8`, `group`,
  `g4`/`g16`/`g64`, `quad`, `qtree`, `gch`, `chunk`), down to `compress`
  (t1) and `compress8` and its keyed copy (state word 13 of every lane).
  Parents keep counter 0, as BLAKE3's do. It is all in the generator
  (`tools/gen_blake3.py`); `hash(a, len)` passes 0.
- **One high word a span, no 64-bit add.** A span never crosses a multiple
  of 2^32 chunks (`cb + nch <= 2^32`), so the low word's adds (`cb + c`,
  `t + 8`, lane `ctr + step * l`) never carry into `hi`. That holds for
  every span anything makes: `b3sum`'s 1 GiB segments are 2^20 chunks at
  multiples of 2^20, and the engine's spans are aligned powers of two of at
  most 2^20 chunks (a BLAKE3 subtree's counter is a multiple of its size).
- **The loader** gives each part `hi = off >> 42` beside `cb = off >> 10`
  (`SLeaf` and the streamed `Part` gain the field) and takes files up to
  2^32 - 1 parts, 4 EiB - 1 GiB: Bend's segment numbers are U32. APFS stops
  at 8 EiB and BLAKE3 at 16 EiB, so this is the limit that binds, and only
  in principle. `b3_segs` splits with a 64-bit count so 2^31+ parts cannot
  overflow it.
- **The engine** builds `SpOne` with `hi` from its 64-bit `cb` (14 fields)
  and exports `b3e_hi()`. The C glue (`blake3_bend.c`) and the Rust bridge
  (`bend.rs`) drop the 2^32 guard, check that the subtree's counter is a
  multiple of the span size, and send the spans; the C glue asks
  `b3e_hi` through a **weak reference**, so a prebuilt engine older than
  this (the Go module's Linux `.syso`, until it is rebuilt) resolves it to
  NULL and keeps 32-bit counters, correct as before.
- The JS engine (`node/js/engine.js`) splits its counter into the two words
  for `span`.

## Proofs and tests

- **Laws.** `compress8.lane` now holds for every `hi` too (2^6,307 inputs:
  each lane takes both counter words); `ob.at` and `ob.go`, the outboard
  tree's hash, for every `hi`; and a new known answer, `kat.span.hi`: one
  chunk at counter 2^32, its high word 1, computed by the checker against
  the official crate's CV. ALL PROOFS CHECK (4 min 12 s on the merged tree).
- **`test/hi.py`**: five spans past 4 TiB through all five trees (CPU
  8-lane, GPU-shaped, outboard, keyed 8-lane, scalar) against the official
  crate's subtree CVs at the same offset (`hazmat`, `test/hiref`): one
  chunk at 2^32; 3 chunks + 5 bytes at 0x2BEEF_FFFFFFF0 (the low word's top
  four chunks); a Leaf32 at 2^32 + 2^31; a full 1 GiB segment at 4 TiB (on
  the GPU tree, its strided lanes, run on the CPU pool); a last segment's
  shape at 12 TiB + 7 GiB. 25/25.
- **`test/huge.py`**: `b3sum` on a sparse file of 4 TiB + 1 GiB + 12345
  bytes with random bytes stamped around the 4 TiB mark and at the ends,
  against the official crate, which reads only the file's data extents
  (`SEEK_DATA`) and hashes each segment at its offset. Identical:
  `90b0b108...49c4cc28`. Bend streamed the 4.4 TB in 241 s (18.2 GB/s,
  holes read as zeros, with the proof checker running alongside); the build
  before this change prints `File too large`.
- The library: `blake3_bend_subtree` at counters 2^32, 5 * 2^32 and 2^50
  (1 EiB) matches the official crate; blake3-bend through `hazmat` offsets
  (default and keyed) matches at 4 TiB, 20 TiB, 1 EiB and just below 4 TiB;
  a misaligned counter falls back. Go: tests pass on macOS (new engine) and
  on Linux arm64 against the old `.syso` (`b3e_hi` an unresolved weak
  symbol). Node's JS engine: 2,100 vector and 2,165 random checks.
- Unchanged: 70/70 official vectors on the CPU and GPU trees; 15/15 big
  files (256 MiB to 8 GiB + 12345 bytes) mapped and streamed.

## Cost

None measurable. `hi` is one more scalar argument down the recursion and
one splatted word in compress8's state instead of a constant 0. On the M5
Pro, against origin/master built the same way, runs interleaved (the
machine was shared: load average 7-13, so CPU numbers swing):

| workload | origin/master | with hi |
|---|---|---|
| 1 GiB in memory, CPU pool, min / median of 12 (3 rounds) | 32.4-35.4 / 35.5-37.4 ms | 32.7-34.4 / 35.5-36.8 ms |
| 256 MiB in memory, one core, min of 5 (3 rounds) | 106.9-124.8 ms | 104.8-112.8 ms |
| 1 GiB in memory, GPU (`hash1!`), min / median of 15 (6 rounds) | 8.41-8.58 / 8.73-8.96 ms | 8.36-8.52 / 8.89-9.03 ms |
| `b3sum` 1 GiB file, cached (hyperfine, 40 runs) | 57.9 ± 8.7 ms | 56.8 ± 2.3 ms |

Every run printed the same digest on both builds.

## Consequences

- `b3sum`, turboblake's file path and the library hash any file up to
  4 EiB - 1 GiB with the official hash.
- The Go module's Linux engines (`engine_linux_{amd64,arm64}.syso`) predate
  this: Go on Linux hashes past 4 TiB through the C library until
  `modal run bend/bench/modal_linux.py --steps go` rebuilds them. (They are
  built on Ubuntu 24.04 and need glibc 2.38; on Debian bookworm they do not
  link, before and after this change.)
- Any new tree in `blake3.bend` takes `hi` beside its counter, and any new
  producer of spans keeps each inside one 2^32-chunk block.
