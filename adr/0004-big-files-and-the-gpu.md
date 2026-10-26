# ADR 0004: Files past 4 GiB, and where the GPU fits

Date: 2026-10-26
Status: accepted

## Context

Movies and disk images are 4-50 GB. v1 took a U32 byte length, so inputs
stopped at 4 GiB, and one Bend array tops out at 2^31 words (8 GiB: the
class field is 5 bits).

## Decision: spans and 1 GiB segments

- The core API is a **span**: an array, a chunk-counter base `cb`, a chunk
  count `nch`, and the bytes in the last chunk `last` (1..1024; 0 for the
  empty input). `chunk` picks 1024 or `last` with a mask, so nothing needs
  64-bit arithmetic. `hash(a, len)` is the convenience for inputs under
  4 GiB.
- The loader cuts a file over 1 GiB into **1 GiB parts** (2^20 chunks),
  each mapped over its own heap block at its file offset. In BLAKE3's
  left-full tree the left side of any node over more than 2^20 chunks is a
  power of two of at least 2^20 chunks, so every part but the last is a
  complete subtree, and the parts' own tree is left-full: the left side
  takes the largest power of two of parts below the count (`b3_segs`).
- Bend hashes the parts with a parallel let and merges them with the same
  `parent` (`b3sum.bend:segs`); only the top merge takes ROOT. Chunk
  counters are U32, so files go to 4 TiB. (ADR 0013 adds the counter's
  high word: files go past 4 TiB.)
- `test/big.py` checks 13 sparse files, 1 GiB - 1 to 8 GiB + 12345 bytes,
  with random bytes at every segment edge: all match the official b3sum.
  A 5 GiB + 1 byte random file: 0.204 s vs 0.219 s.

## Decision: the CLI is CPU-only; the GPU is the throughput path

In memory, warm, `hash1!` on the M5 Pro's 20-core GPU hashes 1 GiB in
12.7 ms (~84 GB/s): 2.2x the official crate's NEON + rayon (27-28 ms,
~38 GB/s). But a GPU-enabled Bend process pays for its Metal heap at
start-up, and that cost grows with the heap: 20 ms at 512 MB, 93 ms at
2 GB, 307 ms at 6 GB, plus 30 ms of dyld and device set-up even when no
bang runs. The heap must hold the input (a mapped file cannot be placed
under an existing Metal buffer), so a one-shot `b3sum` of N GiB would pay
~50 ms per GiB before hashing, against ~45 ms per GiB for the whole CPU
run. So `b3sum` has no `!` and builds as plain C; the GPU path stays the
library entry point `hash1!` for long-running in-memory hashing, where its
set-up is paid once.

## Consequences

- One code path serves every size: a file of up to 1 GiB is one span
  (`FFile`), a bigger one a `Segs` tree (`FSegs`).
- On a GPU heap (no mapping) a large part is read in 4 MiB slices by every
  loader thread instead.
