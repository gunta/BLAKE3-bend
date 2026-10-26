# ADR 0013: turboblake never slower than the official b3sum

Date: 2026-10-26
Status: accepted

## Context

turboblake is the official `b3sum` 1.8.7 on `blake3-bend`, with a fast path
that sends files to the Bend engine. Raced case by case against the official
`b3sum` on the M5 Pro (interleaved medians, `bench/race.py`-style, load 3-14
from other sessions and VMs), the shipped build lost far more often than the
site's tables suggested; those tables raced the pure-Bend `bend/build/b3sum`,
not turboblake:

| case | b3sum | turboblake (shipped) | |
|---|---:|---:|---:|
| empty file | 3.39 ms | 3.57 ms | 0.95x |
| 64 KiB - 16 MiB, one file | 3.8-4.6 ms | 4.5-5.7 ms | 0.80-0.84x |
| 256 MiB, one file | 15.2 ms | 20.6 ms | 0.74x |
| 1 GiB, one file | 48.2 ms | 61.1 ms | 0.79x |
| 1 KiB + 1 GiB | 52.1 ms | 69.1 ms | 0.75x |
| `--keyed` / `--length 64` / `--seek 1`, 1 GiB | 51-55 ms | 84-89 ms | 0.60-0.62x |
| `--derive-key`, 256 MiB | 15.9 ms | 35.4 ms | 0.45x |
| `--check`, 5 x 100 MiB | 33.0 ms | 59.6 ms | 0.55x |
| `--num-threads 4`, 1 GiB | 167 ms | 196 ms | 0.85x |
| stdin / `--no-mmap`, 1 GiB | 536-579 ms | 548-587 ms | tie |

The library had the same problem: `blake3-bend`'s `update_rayon` ran 1.2-1.6x
slower than upstream's from 1 MiB up (1 GiB: 45.3 against 28.9 ms), and the
Python package lost to `blake3` on PyPI with `max_threads=AUTO` at 256 MiB and
1 GiB (0.76x, 0.69x in `lang-python.json`).

## Causes

1. **compress8 out of line.** 0f85be0's keyed tree gave the default tree's
   `compress8` a second caller; clang stopped inlining it (ADR 0002's rule).
   Found here and by the other session at once; its fix (17987ca, ADR 0012's
   addendum) is merged. Alone it took one 1 GiB file from 0.78x to 0.91x.
2. **Every span copied on macOS.** macOS hands big allocations out just
   above a 384 GiB guard (448 GiB up, lowest address first); the engine's heap
   sat at 32 TiB, and its window (the 8 TiB a Term can name past the heap's
   base) never covered the host's memory. So the hook copied everything,
   ~8 ms a GiB, which loses to rayon, and turboblake's upstream paths
   (`--keyed`, `--check`, ...) went through it.
3. **The engine for everything.** Starting the engine costs about what a few
   small files cost upstream, and one big cached file is bound by its page
   faults, which the kernel serializes per file (~15 ms a GiB however many
   threads fault it); the engine takes those no faster than upstream's
   mapping. The residency check alone was 4096 `mincore` calls, 3 ms a GiB.
4. **rayon's threads, always.** Upstream starts 18 rayon threads before the
   first file, ~0.3 ms (`b3sum --num-threads 1` on an empty file: 1.8 against
   2.1 ms).
5. **stdin and `--no-mmap` on one thread.** Upstream's `update_reader` reads
   64 KiB at a time and hashes on one core, ~2 GB/s.

## Decision

### The hook takes only what it wins (blake3-bend, `bend.rs`)

`Join` gets a `PARALLEL` const (true for `RayonJoin`), and the hook's
`subtree` gets it. A rayon caller hands the engine a subtree only when the
engine reads it in place, in the default mode (`flags == 0`: the keyed tree
runs ~2.3x slower per core, 1 GiB keyed in 68 ms against 29), and up to
16 MiB. Past that, after the engine has idled, a job pays up to ~1 ms waking
it: with 5 ms gaps between calls it lost 32-64 MiB (0.77-0.81x) and won
16 and 128 MiB. Everything else stays upstream's code. A serial caller
(`hash`, `update`) still takes the engine for any big subtree, copied or not:
against upstream's one thread it always wins.

### The engine's window covers the host on macOS (`engine.c`, `patch.py`)

When the library loads, a constructor reserves 16 GiB (`PROT_NONE`) at the
lowest hole that fits, and puts `PROT_NONE` placeholders, mapped by hint and
never `MAP_FIXED`, in the holes of 64 MiB or more below it. What the host
allocates afterwards lands above, inside the window: every buffer from 4 MiB
up, `malloc` or `mmap`, in 30 processes of 30 (7 of 30 with the reservation
alone, since libmalloc's own regions sit at random places low in the zone).
`corpus_map` puts the heap in the reservation and `corpus_at` grows it there
(`MAP_FIXED` over our own placeholder); `b3e_inside` knows the window before
the engine starts. A 1 GiB `malloc` buffer: 25.9-26.7 ms in place against
34-38 copied.

The heap cannot grow past the reservation, and a Bend heap that runs out
calls `_exit(1)` in the host. The heaviest sequence measured (copied spans,
2048 x 900 KiB files, a streamed 1 GiB file, repeated) peaks at 4.8 GiB, and
`b3e_heap_room` turns jobs away (the caller hashes as upstream does) once 3/4
of it is used. Linux keeps its placement (7 TiB below where mmap hands out
memory). `BLAKE3_BEND=0` skips the reservation.

### Streams share one pair of blocks (`effs/load.c`)

Each streamed file allocated two 1 GiB heap blocks and kept them: 2 GiB of
touched memory per uncached file, for the life of the process. Streams are
hashed one at a time and a stream's last segment starts no read, so one
pair serves them all; `B3IO.release` also forgets the round's streams.

### turboblake routes each batch (`fast.rs`, `patch_b3sum.py`)

- A batch of arguments (and now of `--check` lines, 2048 at a time) goes to
  the engine when it has more than 16 files, more than 32 MiB past its
  biggest file (the engine overlaps big files' faults, one file's with
  another's), or a file from 256 MiB mostly on disk (`b3e_cached`: the
  loader's residency sample, without starting the engine). Otherwise
  upstream's path hashes it.
- rayon's global pool starts when a file first needs it; `--num-threads`
  still builds its pool up front, as upstream does.
- A file under 1 MiB (128 KiB once rayon runs) is hashed on one thread.
- stdin and `--no-mmap` read 32 MiB blocks on a thread of their own (a
  regular file's with four positional reads at once) while the block before
  hashes on every core with upstream's `update_rayon`. Nothing is mapped;
  stdin is read from its offset to the end and left there.
- The hook stays off in the CLI (`BLAKE3_BEND_MIN` = max unless set): with
  file maps now in the window it would take a single file and pay the
  engine's start (4-64 MiB 0.91x, `--keyed` 1 GiB 0.55x when it was on).
- The residency sample is 256 `mincore` calls (~0.2 ms a GiB), not 4096.

## Results

turboblake against b3sum 1.8.7, interleaved medians (15 rounds, load 8.2;
the 1-16 MiB rows also at 41 rounds):

| case | b3sum | turboblake | |
|---|---:|---:|---:|
| empty / 1 B / 1 KiB / 64 KiB / 256 KiB | 3.3-3.5 ms | 3.2-3.4 ms | 1.00-1.09x |
| 1 / 4 / 16 MiB, one file | 3.7-4.6 ms | 3.8-4.8 ms | 0.96-0.99x (41 rounds) |
| 64 MiB / 256 MiB / 1 GiB, one file | 7.4 / 15.5 / 49.0 ms | 7.4 / 16.1 / 49.7 ms | 0.96-1.00x |
| 5 x 100 MiB | 33.6 ms | 27.5 ms | 1.22x |
| 10k x 100 B | 149 ms | 72 ms | 2.07x |
| 300 mixed files | 82 ms | 26 ms | 3.20x |
| 2k x 64 KiB / 1k x 1 MiB (`race.py`) | 278 / 252 ms | 25.5 / 52.5 ms | 10.9x / 4.8x |
| SDK headers / 8k cargo sources (`race.py`) | 148 / 277 ms | 37 / 70 ms | 4.0x / 4.0x |
| stdin 64 MiB / 1 GiB | 38.5 / 529 ms | 10.1 / 57.4 ms | 3.8x / 9.2x |
| `--no-mmap` 64 MiB / 1 GiB | 37.0 / 543 ms | 10.0 / 59.7 ms | 3.7x / 9.1x |
| `cat file \|` 1 GiB | 517 ms | 334 ms | 1.55x (the pipe's limit) |
| `--keyed`, `--derive-key`, `--length`, `--seek`, `--raw`, `--num-threads` | | | 0.98-1.00x |
| `--check`: 5 x 100 MiB / 10k x 100 B / 300 mixed / 2048 x 900 KiB | 31.3 / 140 / 68 / 647 ms | 28.0 / 69 / 24 / 237 ms | 1.12x / 2.0x / 2.9x / 2.7x |

The library, each crate alone in its process: `blake3-bend`'s `update_rayon`
1-16 MiB 1.3-2.0x faster than upstream's, larger the same code; its `hash`
in place 1 GiB 26-29 ms against upstream `update_rayon` 28-31 (and 438 for
upstream's `hash`). Python against `blake3` 1.0.11, `max_threads=AUTO`,
interleaved at load 13-15: 1 MiB 1.26x, 16-64 MiB 1.00x, 256 MiB 0.93x,
1 GiB 0.97x.

Checks: upstream's CLI tests (17), `check_vectors.py` (35 vectors, stdin,
`--length`, `--check`), every length from 1 byte to 128 MiB + 7 across block
edges on all three read paths, `--check` output and exit codes against b3sum
on good, bad, missing, directory and malformed lines, blake3-bend's tests
(also with every subtree on the engine), libblake3-bend's `test.py --big`
(1525/1525), `go test`.

## Refuted

- **QoS.** Pool threads at user-interactive (the main thread's class):
  slower.
- **always_inline on every `DFAR` kernel.** 2-3x slower: the code blew up.
- **Streaming cached files** in 32-128 MiB segments with 4-16 readers
  (pread, no faults on the file): 48-58 ms for 1 GiB against 42.6 mapped.
- **Ordered segments with prefault helpers** (`madvise(WILLNEED)` ahead of
  `update_rayon` on 64-128 MiB pieces): 38.6-41.8 against 42.3 in one run,
  48.0 against 46.6 in the next; noise.
- **`mach_vm_remap` of the caller's pages into the window**: soft faults
  10.6 ms and unmapping 7.5 ms a GiB, worse than the copy (the other
  session found the same).
- **Oversubscribing the engine** (36-128 threads): helps in-memory spans
  under load (18 threads 38.5 ms, 128 threads 32 ms) but slows mapped files
  (63 -> 69-75 ms) and, in the Python race, small inputs.
- **Exiting without `munmap`**: teardown at exit costs the same 4.6 ms a GiB.

## Consequences

- No measured case is slower than b3sum beyond noise. One cached big file
  is a tie, not a win: page faults serialize per file in the kernel
  (`madvise(WILLNEED)` from 16 threads: 14.6 ms a GiB), unmapping costs
  4.6 ms a GiB, and hashing ~29 ms a GiB on every core; neither side can
  avoid them. 1-16 MiB single files sit 1-4% behind at 41 rounds: the
  engine's code costs ~0.3 ms of startup even with `BLAKE3_BEND=0` (an empty
  C program: 1.4 -> 1.8 ms when it links libblake3-bend); not yet traced.
- Under heavy outside load the engine falls behind rayon's work stealing on
  big inputs (Python 256 MiB-1 GiB 0.93-0.97x at load 13-15); on a quieter
  machine it led (1 GiB 26-27 against 27.7-29 ms).
- Open for the engine: the keyed tree's per-core speed (2.3x behind the
  default tree), and the ~1 ms a job pays after the engine idles.
- Every process that links blake3-bend on macOS reserves 16 GiB of address
  space and a few placeholders (~2 GiB) at load; no memory.
- The Linux Go objects (`engine_linux_*.syso`) predate the stream-block fix;
  `bend/bench/modal_linux.py --steps go` rebuilds them. The Windows build of
  the new reader code (`cfg(not(unix))` falls back to upstream's) is not
  compiled here: no Windows target installed.
- Measured with other sessions, VMs and an emulator on the machine (load
  3-15): the ratios are interleaved, the absolute numbers drift ±15%.
