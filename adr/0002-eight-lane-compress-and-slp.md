# ADR 0002: Eight-lane compress8, shaped for clang's SLP vectorizer

Date: 2026-10-26
Status: accepted

## Context

After ADR 0001 the CPU path was scalar: one chunk at a time, 1.2 GB/s per
core against the Rust crate's 2.35 GB/s (NEON, four chunks per vector).
Bend has no vector types (`U32`, `F32`, `Nat` only), so SIMD can only come
from clang auto-vectorizing the C that bend emits.

What we measured, in order:

1. A hand-written C microbenchmark of N-lane interleaved scalar BLAKE3:
   default flags never vectorize it (1-lane 1.21 GB/s, 4-lane 1.44,
   8-lane 1.22). With `-mllvm -slp-threshold=-1000
   -slp-recursion-max-depth=100000`, 8 lanes reach 2.70 GB/s, but 1-lane
   code drops to 0.45 GB/s: a global flag that is not free.
2. The same idea in Bend did not vectorize at all. Remarks showed why:
   SLP starts from runs of consecutive stores. Bend returns a record
   through `Term o[]` (64-bit slots), so a 128-bit register holds two
   seeds and the trees stay 2 wide (`.2s`).
3. Masked array indexing (`i & (2^cls - 1)`, every `a[i]`) is *not* the
   problem: the C microbenchmark with masked loads still reaches 2.1-2.3.

## Decision

- `compress8` runs eight compressions with each G operation emitted for
  all eight lanes back to back.
- `CV8` and `B128` fields are **word-major** (word 0 of all lanes, then
  word 1, ...), so the result stores of a lane bundle are adjacent.
- Build flags (in `bend/build.sh`): `-mllvm -slp-max-reg-size=512`
  (an 8 x i64 seed), `-slp-recursion-max-depth=100000` (the tree is ~1700
  instructions deep), `-slp-threshold=-20`.
- The chunk loop `c8.go` has a *single* `compress8` call site. The END
  flag comes from a helper on the loop counter, and the loop over-reads one
  block past the group (dropped). Parents use `compress8.p`, a body of its
  own (no counters), because bend deduplicates identical spins and would
  otherwise give `compress8` three call sites.
- The CPU tree (`tree8`) stops at full 32-chunk subtrees (`leaf32`: four
  8-chunk groups, two `par8` levels, then `fold8`, seven 1-lane parents)
  or full 8-chunk ones (`leaf8`). Partial subtrees descend to 1-lane
  chunks. A wide leaf requires every chunk to be full of bytes (found by
  the 7169-byte vector, where 8 chunks ended in a 1-byte one).
- The GPU keeps the 1-lane tree (`hash1`): eight lanes per GPU thread
  would only spill registers.
- The Bun-based checker needs a deep stack for a 3600-let def:
  `ulimit -s 65520` and `JSC_maxPerThreadStackUsage=60000000`.

## Results (256 MiB in memory, digests identical to Rust)

| implementation                  | 1 thread          | 18 threads        |
|---------------------------------|-------------------|-------------------|
| Rust blake3, NEON (+ rayon)     | 114 ms (2.35 GB/s)| 7.7 ms (35 GB/s)  |
| Bend v1, 1-lane tree            | 225 ms (1.19)     | 25.3 ms (10.6)    |
| **Bend v2, compress8 + SLP**    | 148 ms (1.82)     | **10.8 ms (25)**  |

The 18-thread gain is bigger than the 1-thread one because the wide leaves
also cut forks by 32x (one task per 32 KiB, not per KiB).

## Consequences

- A stale-file bug hid two experiments: `build.sh` kept the old `.c` when
  bend failed. It now deletes it first and prints bend's errors.
- The SLP flags are global: they also touch the runtime and the 1-lane
  code. Every change is checked against the 1-thread and 18-thread runs
  and the 70 test vectors (35 per path).
- Still 1.3x behind NEON per core: 128 scalar masked loads per block and
  the marshalling around `ld8` are the next targets.

## Addendum: the inline threshold (same day)

Profiling the v2 build showed `compress8` at ~49% of samples and the
loader/loop at ~45%: the block's 128 words came back from `ld8` through
`o[]`, went out again as 196 stack arguments, and the CV8 came back through
`o[]`. Fully inlining `compress8` into the loop (`-inline-threshold=40000`)
is worse (268-288 ms): Bend's tail loop carries the lanes through phis, so
the loop body has no stores to seed SLP. The out-of-line `compress8`, whose
`o[]` stores are the seeds, is structural. In between, the threshold
matters a lot and not monotonically (256 MiB, 1 thread / 18 threads):

| -inline-threshold | 1T      | 18T     |
|-------------------|---------|---------|
| default (487)     | 148 ms  | 10.8 ms |
| 3000              | 135     | 10.0    |
| 6000              | 128     | 8.6     |
| 10000             | 150     | 10.0    |
| 15000             | 93      | 7.0     |
| **20000**         | **92**  | **6.4** |
| 25000             | 93      | 6.7     |
| 40000             | 288     | 23.9    |

20000 is the default in `build.sh` now. At 1 GiB in memory: Bend 1 thread
377 ms (2.85 GB/s) vs Rust NEON 448 ms (2.40 GB/s); 18 threads 27.2 ms vs
Rust rayon 27.3 ms. The CPU path no longer trails the official crate.
