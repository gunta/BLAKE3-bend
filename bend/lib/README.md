# libblake3-bend

The official BLAKE3 C library (`c/` in this repository, `blake3.h`
unchanged), with one change: when an update reaches a big complete subtree,
the part BLAKE3 can hash in parallel, the subtree goes to a Bend2 engine
that hashes it on every core. Everything else is upstream's code: the
chunk state, the CV stack, keyed hashing and key derivation, finalization,
extended output. Programs written against `blake3.h` relink and run
unchanged; same symbols, same `blake3_hasher` layout.

```bash
bend/lib/build.sh
```

builds `bend/lib/build/lib/libblake3.a` and `libblake3.{dylib,so}`, with
`include/blake3.h`, and `bin/blake3` (a test CLI). To use it in place of
the official library, point your build at those:

```bash
cc -I bend/lib/build/include app.c bend/lib/build/lib/libblake3.a -lpthread -o app
```

## How it works

- `blake3.c`'s `compress_subtree_to_parent_node` asks `blake3_bend_subtree`
  (`blake3_bend.c`) first. That cuts the subtree into spans of at most
  1 GiB, each a whole subtree, hands them to the engine in one job, and
  merges their CVs into the two child CVs upstream expects.
- The engine (`engine.bend`, `engine.c`) is a Bend program that runs on a
  thread of its own for the life of the process: `Eng.next` waits for a
  job, Bend hashes every span at once (`H.hash.at`, the 8-lane tree),
  `Eng.done` hands the CVs back.
- Bend's arrays live in an 8 TiB window past its heap's base. On Linux the
  engine puts that window over the region where `mmap` (and so `malloc`)
  places big buffers, and reads the caller's memory where it lies: no
  copy. On macOS every big allocation sits below 512 GiB, where no heap can
  go, so spans are copied (by a few helper threads) into two warm heap
  blocks.
- The engine starts on the first big update. Before that, and for small
  subtrees, keyed hashing and key derivation (for now), and in a forked
  child, the official C code hashes as it always does.
- The smallest subtree worth a trip to the engine is calibrated once: the
  engine's fixed cost per job against the C code's one-thread rate.
- The library build patches Bend's emitted C (`patch.py`) so it can live
  inside another program: no process-wide signal handlers.

Environment: `BLAKE3_BEND=0` turns the engine off, `BLAKE3_BEND_MIN=<bytes>`
sets the threshold, `BLAKE3_BEND_THREADS=<n>` caps the engine's threads,
`BLAKE3_BEND_TRACE=1` prints the calibration and the jobs.

## Test and benchmark

```bash
python3 bend/lib/test.py --big
```

```bash
python3 bend/lib/bench.py
```

`test.py` runs every official test vector in all three modes, with
extended output and a seek, under seven update splits, with the engine
taking every subtree of two chunks or more, then random inputs up to
2 GiB + 1 against the official `b3sum`. `bench.py` hashes one in-memory
buffer per size through the same `blake3.h`, against the official C
library (SIMD, one thread: it has no threads of its own without TBB).

| one update, in memory | official C | libblake3-bend | |
|---|---:|---:|---:|
| 1 MiB, M5 Pro | 0.497 ms | 0.179 ms | 2.8x |
| 64 MiB, M5 Pro | 28.0 ms | 2.83 ms | 9.9x |
| 1 GiB, M5 Pro | 481 ms | 38.7 ms | 12.4x |
| 1 GiB, Linux x86-64 (Modal) | 323 ms | 25.6 ms (no copy) | 12.6x |

(The Mac numbers were taken with other work running at a load average
near 7.)
