# ADR 0006: Native Metal and CUDA references for the GPU path

Date: 2026-10-26
Status: accepted

## Context

`hash1!` hashes 1 GiB in ~12.5 ms on the M5 Pro's GPU, 2.2x the official
crate on every CPU core (ADR 0005), but nothing said what the GPU itself
can do, so nothing said where Bend's GPU path or the Bend runtime should
look next. The hash in `b3sum` stays in Bend; these are yardsticks.

## Decision

`bend/ref/` holds native GPU BLAKE3 implementations to race against:

- `b3core.h`: the compression, one header that builds as Metal, CUDA and
  plain C (rounds written out with their message indices).
- `metal/`: `b3.metal` (kernels) and `b3metal.m` (host). The source is
  embedded and compiled by the driver at start-up (`build.sh`), so no
  offline Metal toolchain is needed.
- `cuda/`: `b3.cu` and `b3cuda.cu`, the same kernels for NVIDIA.
- `cpu_test.c`: the kernels' tree logic on the CPU, a 32-lane group emulated
  lane by lane, against the official vectors.
- `race_gpu.py`: Bend's `bench/mem` against the Metal reference, interleaved.

The kernels: a leaf thread hashes K chunks one after another and folds them
with a CV stack (as the reference implementation does); the 32 lanes of a
SIMD group fold their CVs with shuffles; a merge kernel repeats the SIMD
fold until one node is left. Pairing a level's nodes and carrying an odd
one up is the same left-full tree, so every dispatch knows which merge is
the root. Metal passes the 35 official vectors at K = 1, 4, 16 and 64, and
in every load and leaf variant below.

## Results (M5 Pro 20-core GPU, warm, in memory, same digests)

`ref/race_gpu.py 6`, medians of 6 interleaved rounds of 8 hashes. An Android
emulator held ~13 cores the whole time, so read these as +-10%.

| input   | Bend `hash1!` | native, Bend's leaves | native, K = 4 |
|---------|---------------|-----------------------|---------------|
| 16 MiB  | 1.29 ms       | 0.41 ms               | **0.37 ms**   |
| 64 MiB  | 1.52 ms       | 0.73 ms               | **0.66 ms**   |
| 256 MiB | 2.70 ms       | 1.80 ms               | **1.72 ms**   |
| 1 GiB   | 12.82 ms      | 8.95 ms               | **6.04 ms (178 GB/s)** |

"Bend's leaves" is the native kernel in `hash1!`'s shape: one thread per
leaf of 4^j chunks, ~2^14 leaves, as `level` picks them.

## Where Bend's GPU time goes (1 GiB, medians)

| experiment                                                      | ms        |
|-----------------------------------------------------------------|-----------|
| native hash, 262144 threads x 4 chunks                           | 6.0       |
| native, reads alone, 1M threads x 1 chunk (`roof_read`)          | 5.5-6.8   |
| native hash, Bend's shape: 16384 threads x 64 chunks             | 8.8-9.8   |
| native, reads alone, Bend's shape                                | 9.0-9.7   |
| native, reads alone, Bend's shape, chunks interleaved over threads (`roof_stride`) | 5.6-6.5 |
| native, reads alone, Bend's shape, a redirect-cell load before each word (`roof_redir`) | 10.1 |
| native, compressions alone, Bend's shape (`roof_alu`)            | 4.4-4.9   |
| Bend, a 2^14-leaf fork tree like `hash1!`'s, leaves that only read (`B3.ld`) | 11.4-12.3 |
| Bend, the same tree, leaves that only compress (1024 each)       | 4.2-4.5   |
| Bend `hash1!`                                                    | 12.5-12.8 |

1. **The hash is bound by reads**, natively and in Bend: the compressions
   run under the loads. Bend's compute is already native speed (4.2-4.5 ms
   against 4.4-4.9 in the same shape), and its hash takes as long as its
   reads alone.
2. **The lane cube's shape costs ~1.5x.** 16384 lanes that each stream
   their own 64 KiB keep live reads spread over the whole GiB. The same
   16384 threads reading interleaved chunks run at full speed, so it is
   locality (DRAM pages, TLB reach), not the lane count: 2 or 4 chunks
   interleaved inside a lane (more loads in flight) changed nothing.
3. **Bend's array reads cost ~1.3x a native read in the same shape**
   (11.4-12.3 against 9.0-9.7). A lane reads its `Array.fork`ed input through a
   redirect cell (`term_peek` in `blk_loc`); a load of such a cell before
   each word costs the native read ~10%, so that is a part of it.
4. **A bang costs ~0.9 ms of fixed time**, which is all of the gap below
   64 MiB.

## Tried, no gain

- A bigger cube for Bend: the generated C patched to 2^8 or 2^9 groups of
  128 lanes (`CUBE` and the stacks sized to match), with `level` aimed at
  2^15 or 2^16 leaves. 4 MiB got faster (1.25 -> 0.78 ms), 64 MiB to 1 GiB
  25-45% slower (1 GiB 12.9 -> 14-17 ms), even with the old leaves: some
  per-lane cost grows with the cube.
- 16-chunk leaves at 1 GiB on the stock cube (65536 leaves): 12.2-12.9 ms
  against 12.5-13.2, and slower at 64 and 256 MiB. ADR 0005's sizes stand.
- Natively, none of these moved the hash past noise: `coherent(device)`
  pointers (how Bend declares its heap on Metal 3.2+), 4-byte instead of
  16-byte loads, a `noinline` compress returning through an array of 64-bit
  terms (how a long spin with several callers compiles on the device), a
  Metal-allocated buffer instead of no-copy host memory, threadgroups of 32
  to 1024 (+-10%).

## The GPU and files

The native kernel hashes a page-cached 1 GiB file, mapped and wrapped
with no copy, in 5.3 ms of GPU time, but the first GPU touch of the mapping
costs ~37 ms more, and a whole process ~80 ms, against 50-60 ms for the
official `b3sum` and Bend's. So `b3sum` stays on the CPU (ADR 0004) even
against an ideal GPU path.

## Ideas for Bend's runtime

- Deal a bang's tasks so that lanes running together read neighbouring
  memory, for example grow past the cube and run the frontier in address
  order: up to ~1.5x for streaming bangs like this one.
- Resolve a forked array's redirect cell once per flat loop instead of once
  per read.
- Find the per-lane cost that grows with the cube before raising it; a
  bigger cube helps small bangs.
- The fixed ~0.9 ms per bang is the whole gap for inputs under ~64 MiB.

## Consequences

- No change to the Bend code: its GPU path is at what the runtime allows.
- The CUDA kernels compile to PTX (sm_80, `cuda/build.sh --ptx`) and their
  logic passes `cpu_test.c`, but they have not run: this machine has no
  NVIDIA GPU. Its first numbers belong in this ADR.
