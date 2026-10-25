# ADR 0009: Streaming files that are not in the page cache; a GPU daemon

Date: 2026-10-26
Status: accepted

## Context

The headline workload is real model weights: here, shards of
`deepseek-ai/DeepSeek-V4.1-Flash-1017` (MIT), fetched with
`bench/hf_fetch.py` (8 parallel range requests, SHA-256 checked against the
Hub): shards 1-6 (31.3 GB) and shard 48, one 101.5 GB file. The Mac has
64 GB of RAM, so such files are mostly *not* in the page cache, and every
earlier path (ours and `b3sum`'s) read them through page faults on a mapping.

Measured on the 101.5 GB shard: the official `b3sum` (mmap + rayon) took
526 s and then 211 s (~0.2-0.5 GB/s, 1466 s of kernel time in faults); on
the 31.3 GB set, Bend's mapped path was 1.42x *slower* than `b3sum` (59 s vs
42 s), because its fork tree faults in pages all over six files at once.
Yet the SSD gives, through `pread`: 8.3 GB/s from one thread with 16 MiB
reads, 10.4 GB/s from 16 threads with 4 MiB reads, and 13.7 GB/s from 16
threads with 16 MiB reads and `F_NOCACHE`. Page faults read 16 KiB at a time.

## Decision: stream what is not cached

- A file of 256 MiB or more is checked with `mincore` on 4096 sampled pages;
  under 90% resident, it is streamed instead of mapped (`B3IO_STREAM=always`
  or `=never` overrides this for tests).
- A stream is the file's 1 GiB segments (each a complete BLAKE3 subtree but
  the last, ADR 0004). `B3IO.seg(id, k)` hands Bend segment k in one of two
  reused heap blocks and, before returning, starts reading segment k + 1 into
  the other on 16 threads of 8 MiB `F_NOCACHE` preads. The SSD fills one
  block while all cores hash the other.
- Bend merges the segment CVs as BLAKE3's own `Hasher` merges chunks: a
  stack of complete subtrees, merged lazily (only when the next segment
  arrives, while the count so far is even), so the final fold knows which
  parent is the root. One segment alone is hashed as the root.
- `F.hash` leaves a streamed file as `OStream`, so the cached files still
  hash in parallel first; `F.fill` then streams each `OStream` in turn,
  every one with the whole SSD and every core.

`test/big.py` checks both paths, mapped and forced-streamed, on 15 sizes from
256 MiB to 8 GiB + 12345 bytes (single-segment streams included) against the
official `b3sum`: all identical.

## Results (one-shot `b3sum`, identical hashes)

| input | official b3sum | Bend b3sum |
|---|---|---|
| DeepSeek shard 48, 101.5 GB | 211.4 s (526 s on its first run) | **7.1-8.2 s** (~13-14 GB/s) |
| DeepSeek shards 1-6, 31.3 GB, median of 3 | 23.4 s | **4.17 s** (5.6x) |

## Decision: a GPU daemon

A daemon pays the GPU's set-up once, so the GPU becomes worth its copy: a
Metal heap cannot take a file mapping, but a parallel `pread` into heap
pages that are already faulted in runs at ~40 GB/s (25-27 ms per GiB; into
fresh pages, 85 ms). So in daemon mode on a GPU heap, `B3IO.again` keeps one
block per (kept path, part) across rounds, holding a reference so Bend never
frees it, and refills it each round; `bench/daemon_gpu.bend` hashes the whole
Files tree in one bang (`F.hashg!`, the GPU-shaped `hash1` trees). A 1 GiB
file: ~30.4-31.2 ms a round, against 47-52 ms for Bend's CPU daemon and
44.4 ms for rayon-parallel Rust.

## Consequences

- Streaming only runs on a CPU heap and outside daemon mode; a streamed file
  has no bao outboard yet (`hash_ob` reports it as an error).
- The decision is per file at load time; a file that is half cached streams.
