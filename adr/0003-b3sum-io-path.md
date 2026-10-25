# ADR 0003: The b3sum I/O path

Date: 2026-10-26
Status: accepted

## Context

`bend/b3sum.bend` must print what the official `b3sum` prints, byte for
byte, and beat it end to end: one big file, and thousands of small ones.
Base's `File.read_bytes` answers a `List` cell per byte, far too slow, so
the bytes come in through custom effects (`bend/effs/*.c`), which the guide
allows: "you can add your own effects the same way". The rule we hold to:
**effects move bytes; every BLAKE3 compression runs in Bend.**

## Decision

`B3IO.load(paths, threads) -> IO(Files)` (`effs/load.c`):

- **One pass per file on a pthread pool:** open, fstat, allocate, read,
  close. The heap allocator is per thread (`Env.alc`); each loader thread
  takes an `ALC` row past the pool's (`pool_size..CUBE_T` are never used on
  the CPU), and the pool itself is parked while an effect runs.
- **Big files are mapped, not read.** A file part of 1 MiB or more is
  `mmap`ed `MAP_SHARED|PROT_READ|MAP_FIXED` over a page-aligned heap block
  (the effect bumps the heap past up to 15 KiB to align it), so the Bend
  `Array<U32>` *is* the page cache. A 1 GiB private (copy-on-write) map
  costs 5 ms to set up; a shared read-only one costs nothing and faults
  ~15% faster. A freed block takes a free-list link in its first word, so
  the loader keeps one reference to every mapped array (`term_keep`): it is
  never freed. Only on a CPU heap: a GPU heap is a Metal buffer.
- **The tree is balanced by bytes**, so the fork over it splits work
  evenly between a few big files and many small ones.
- **Names are the argument Strings themselves**, read in place, not
  rebuilt: rebuilding 10,000 names cost 7.5 ms.

`B3IO.emit(o: Out) -> IO(U32)` (`effs/emit.c`) writes every line in one
`write`. Building ~940k `SCon` cells in Bend and printing them cost
~15 ms for 10,000 files. emit only formats the CV's words as hex (the
byte order is BLAKE3's own output order). Bend flattens the `CV` record
into its parent constructor (`OHash` has arity 9, not 2); emit reads
either layout.

Build: a program with no `!` call compiles as plain C (`-x c`, no Metal,
no Foundation), which takes start-up from 2.7 ms to 1.4 ms (`b3sum`: 1.9).

## What we measured about macOS opens

`open()` is the floor for small files, and it is not ours to remove:

- 10,000 opens of 4 KiB files: 125-153 ms on one thread, a floor of
  ~48-60 ms on 18 threads. Threads and **processes** scale the same, so it
  is not the per-process fd table; 16 directories instead of one change
  nothing, so it is not a directory lock; outside the tool sandbox it is
  the same. The serialization is volume-wide, in the kernel.
- `openat()` on a directory fd, dropping `fstat`, dropping `close`: all
  within noise.

So the small-file path is: parallel opens at the kernel's floor (~49 ms of
a ~56 ms run for 10,000 files), with everything else (args 0.8 ms, tree
1.1 ms, hashing 2.7 ms, output) cut to the bone.

## Results (interleaved medians, `bench/race.py`, load average ~6)

| workload       | b3sum    | Bend b3sum | result          |
|----------------|----------|------------|-----------------|
| 10k x 4 KiB    | 150.6 ms | 77.3 ms    | 1.95x faster    |
| 2k x 64 KiB    | 285.9 ms | 28.4 ms    | 10.1x faster    |
| 64 MiB file    | 6.8 ms   | 6.8 ms     | tie             |
| 1 GiB file     | 47.2 ms  | 46.3 ms    | 1.02x faster    |

## Rejected

- Pre-faulting mapped pages from the loader (1-18 threads), detached
  prefetch threads while Bend hashes, `madvise(WILLNEED)` (98 ms for
  1 GiB) and `mlock` (48-156 ms): page faults on one file serialize in
  the kernel, ~15 ms per GiB however they are taken. `b3sum` pays the
  same.
- Reading big files with `pread` into heap blocks: 70 ms per GiB.
- Dropping the runtime's array index mask (`blk_at`): no change, so the
  runtime stays untouched.
