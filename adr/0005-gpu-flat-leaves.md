# ADR 0005: Flat GPU leaves, sized to the lane cube

Date: 2026-10-26
Status: accepted

## Context

`hash1!` forked all the way down to single chunks: a task per KiB, 1M
tasks per GiB. The shaders guide: a bang runs a cube of 16384 lanes; a
kernel iteration grows the fork tree breadth-first until the frontier fills
the cube, then each lane runs its task to the end, and a continuation that
forks again lands in the next iteration. "Aim for 4^7 leaves per bang, one
per lane"; fewer leave lanes idle.

## Decision

- Sequential leaves with no fork: `gch` (one full chunk), `g4`, `g16`,
  `g64` (four of the level below, then two levels of parents). Arrays are
  affine, so each is a chain of one-step defs threading the array handle,
  the same pattern as the CPU's `leaf32`.
- `treeg` forks down to full subtrees of the **leaf level** and hands each
  to one lane. The level adapts to the input so there are about 2^14
  leaves: `level(k) = 2 * floor((clamp(k, 14, 20) - 14) / 2)` chunks-depth,
  i.e. 4-chunk leaves at 64 MiB, 16 at 256 MiB, 64 from 1 GiB up. Partial
  subtrees (the input's tail) still split down to chunks.

A first try with fixed 64-chunk leaves made 64 MiB 2.5x slower (2.9 ms vs
1.2): 1024 leaves for 16384 lanes.

## Results (warm, in memory, GPU, digests checked against Rust at 1-256 MiB)

| input    | per-chunk tasks | flat leaves         |
|----------|-----------------|---------------------|
| 64 MiB   | 1.13-1.2 ms     | 1.21 ms             |
| 256 MiB  | 2.6-3.8 ms      | **2.43 ms (110 GB/s)** |
| 1 GiB    | 12.7 ms         | **11.6 ms (93 GB/s)**  |

Rust blake3 (NEON + rayon) on the same 1 GiB: 27-28 ms. The GPU path is
2.4x the fastest official implementation on this machine.
