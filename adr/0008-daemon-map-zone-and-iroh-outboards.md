# ADR 0008: The daemon race, a zone for mapped files, and iroh outboards

Date: 2026-10-26
Status: accepted

## Context

The one-shot `b3sum` race includes process start-up, and the official
`b3sum` hashes files one at a time. The likely real use is a long-running
service (a sync daemon, an iroh node) that re-hashes what it watches. So we
added a race with start-up excluded, against the strongest Rust baseline we
could write, and an iroh-blobs ingest race.

## Decisions

**The daemon race** (`bench/daemon.bend`, `bench/rust/src/bin/daemon.rs`,
`bench/daemon.py`). One process per side runs N rounds; each round re-opens
and re-maps (or reads) every file, hashes it, and releases it, and prints the
XOR of all hash words, which must agree across sides. The Rust side runs
either one file at a time (as `b3sum`) or rayon across files with
`update_mmap_rayon` inside each (mmap above 16 KiB). Bend keeps the paths once
(`B3IO.keep`) and re-loads them each round (`B3IO.again`), then
`B3IO.fold` and `B3IO.release`.

**A zone of its own for mapped files.** A daemon round over 1,000 x 1 MiB
files spent 23-25 ms in the loader: every file was `MAP_FIXED` into the heap's
single big reservation, so the kernel split that VM entry, under the VM map's
lock, per file, and release split it again. Files now map into empty address
space 6 TB past the heap (still inside a Term's 2^40-word reach), only hinted,
never forced; consecutive files get consecutive ranges, so a round releases
with one `munmap`. Loader time: 23-25 ms -> 5 ms; the round: 63 -> 45 ms
(Rust rayon: 43.5). compress8's chunk loop no longer reads a block past its
chunks, so no read ever leaves a mapped file. Files under 1 MiB are still
read, not mapped: mapping 64 KiB files cost 17 ms a round against 13.2.

**iroh-blobs outboards in Bend.** iroh-blobs 0.103 ingests a file
(`add_path`) by hashing it and building its bao outboard on one core:
717-1052 ms for a 1 GiB file, ~1.4 GB/s. The outboard is the pair
(left CV, right CV) of every parent above 16 KiB chunk groups, in pre-order:
BLAKE3's own parents of level 5 and up, which Bend's CPU tree computes
anyway. `tree8o` keeps them as an OB tree (pair, left side, right side) as it
goes; `fold8o` keeps a 32-chunk leaf's top pair; files past 1 GiB add their
segment merges. `bench/obao.bend` writes them; `bench/iroh` `ob-check`
compares them with bao-tree 0.16 (what iroh-blobs 0.103 uses): 34 files from
0 bytes to 5 GiB, every 16 KiB boundary, byte-identical.

Bend effects can only name constructors of their own module (`CID`), and OB
lives in `blake3.bend`; but OB's only other constructor is nullary, so the C
walker tells a node by its tag, and reads the flattened layout (Bend
flattens a CV record into its constructor: `ONode` has arity 18) from the
arity table.

## Results (medians, M5 Pro, the machine also downloading at 100 MB/s)

| workload, ms per round | Rust seq | Rust rayon | Bend |
|---|---|---|---|
| 1 GiB file | 47.4 | 44.4 | 44.9 |
| 64 MiB file | 3.2 | 3.1 | 3.0 |
| 10,000 x 4 KiB | 144.3 | 51.8 | 53.5 |
| 2,000 x 64 KiB | 292.4 | 12.7 | 13.2 |
| 1,000 x 1 MiB | 252.7 | 43.5 | 45.0 |
| cargo sources | 273.8 | 41.5 | 43.4 |

Against rayon-parallel Rust the daemon race is a tie within a few percent:
both sit on the same floors (open(), page faults, the all-core ceiling).
