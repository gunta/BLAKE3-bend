# ADR 0011: What Bend can do that the Rust crate does not: strided GPU lanes, and the CPU and the GPU on one input

Date: 2026-10-26
Status: accepted

## Context

The question: reading the BLAKE3 paper from first principles, is there a
faster BLAKE3 that Bend can express and the official Rust crate cannot?

What the paper fixes, and what it leaves free:

- **The work is irreducible.** Every chunk's CV depends on its chunk
  counter (§7.5), on purpose: identical or all-zero chunks at different
  offsets have different CVs, so no implementation may share work between
  them ("BLAKE3 deliberately sabotages these tricks", to stay constant-time).
  An input of N chunks costs 16N block compressions plus N - 1 parents,
  whatever the language. The only levers are each device's throughput and
  how many devices run at once.
- **The order is free.** The tree is fixed (§2.1: left subtrees full and
  big), but any schedule that computes the same nodes is BLAKE3: §5.2's
  recursive split, §5.1.2's CV stack, a level-by-level reduction.
  Parallel hashing is choosing which processor computes which node, and in
  what order it reads the bytes.

What Bend has that the Rust crate does not: one source that runs on the CPU
(clang packs `compress8` into NEON, ADR 0002) and on the GPU (`!`, Metal),
on one unified heap; and a checker that proves tree identities (ADR 0007:
`segments`, `levels`), so a new schedule can lean on a law instead of on
luck. The crate has no GPU path at all.

So we tried two schedules the crate cannot run: the CPU and the GPU hashing
one input together, and GPU lanes assigned for memory locality instead of
by subtree.

## Decision 1: strided GPU lanes for big subtrees

ADR 0006 measured that `hash1!` is read-bound, and that its lane shape costs
~1.5x. Each of 16384 lanes streams its own 64 KiB, so live reads spread over
the whole GiB. `ref/metal`'s new `roof_group` and `roof_ghash` kernels keep
that shape (16384 threads x 64 chunks) but let thread t read G-chunk groups
t, t + T, t + 2T, ... (1 GiB, medians of 6, `B3_G=G b3metal roof 28 7 64`):

| G (chunks a group) | reads alone | reads + every compression |
|--------------------|-------------|---------------------------|
| 64 (Bend's leaves) | 9.58 ms     | 9.66 ms                   |
| 16                 | 5.69 ms     | 6.41 ms                   |
| 4                  | 5.65 ms     | 5.91 ms                   |
| 1                  | 5.52 ms     | 5.88 ms                   |

16-chunk groups recover nearly all of it. In Bend that is a schedule, not a
runtime change. At leaf level 6 (inputs past 512 MiB), a whole subtree of
64 S chunks goes to S lanes (`GQuad` in `blake3.bend`'s `treeg`). Lane l
hashes the groups l, l + S, l + 2S and l + 3S with the existing `g16` leaf
and returns their four CVs (`CV4`, 32 words: a record, so no lists). The
fork over the lanes is the tree over lane numbers. A join (`par4`) pairs its
halves' four CVs group for group: BLAKE3's tree of groups, built level by
level (the `levels` law). After log2(S) joins the four CVs are the subtree's
quarters, and `fold4` takes two more parents. A lane does the same work as
a 64-chunk leaf (64 chunks, 60 parents); a join does 4 parents instead of 1.

Results (warm, in memory, digests equal throughout; the machine under heavy
outside load, so read the A/B, not the absolute numbers):

| input | `hash1!` before | `hash1!` after | interleaved rounds |
|-------|-----------------|----------------|--------------------|
| 1 GiB | 13.1-13.4 ms    | **9.1-9.9 ms** | 3 x 10 hashes      |
| 2 GiB | 31.5-33.3 ms    | **19.1-20.2 ms** | 3 x 10 hashes    |

`ref/race_gpu.py 6` in the same session (medians):

| input   | Bend before | Bend after          | native, Bend's old leaves | native, K = 4 |
|---------|-------------|---------------------|---------------------------|---------------|
| 64 MiB  | 1.62 ms     | 1.63 ms             | 0.74 ms                   | 0.73 ms       |
| 256 MiB | 2.85 ms     | 2.96 ms             | 1.97 ms                   | 1.90 ms       |
| 1 GiB   | 13.15 ms    | **9.43 ms (114 GB/s)** | 9.19 ms                | 6.69 ms       |

At 1 GiB Bend now runs as fast as hand-written Metal in Bend's old lane
shape. The rest of the gap to native (1.4x) is the array-read path and the
cube (ADR 0006).

Correctness: the official vectors (70/70); `ALL PROOFS CHECK`;
`test/split.bend`'s ten inputs past the vectors (128 KiB to 1 MiB, odd
tails), whose GPU share at leaf level 6 takes `GQuad`, against the CPU tree;
and `bench/gpusum` (b3sum, hashed by `hashg!` on the GPU), whose output is
byte-identical to the official `b3sum` on random files of 768 MiB,
1 GiB + 12345, 1.5 GiB + 1 and 3 GiB - 7 bytes.

Tried, not kept:

- The stride below the full cube: 256 MiB on 4096 lanes 5.3 ms against
  3.0 ms, 512 MiB on 8192 lanes 7.2 against 6.2. Fewer lanes cost more than
  locality gains. `GQuad` applies only at leaf level 6, with as many lanes
  as 64-chunk leaves would take.
- Two groups a lane at 512 MiB (16384 lanes): 5.1-5.3 ms against 5.6. Its
  16-chunk leaves already sit on adjacent lanes, so +7% did not earn a
  second record type.

## Decision 2: the CPU and the GPU on one input

`split.bend` cuts BLAKE3's tree along its right spine. From the root, every
node's left child is a complete subtree and its right child is the next node
of the spine. A plan (`j`, owner bits) gives each of the first j left
children, and the remainder, to one device. Each side hashes only its own
subtrees, the GPU's in one bang; `merge` folds the two CV lists back up the
spine, ROOT on the top. Any dyadic split works: 3/4 of a power-of-two input
on the GPU is plan `2:3`.

Two findings set the design:

- **A bang holds its run.** `corpus_eval` runs a bang synchronously on the
  host thread, and a bang reached after a fork runs on the CPU pool (the
  shaders guide says the same). One Bend run cannot keep both devices busy,
  and `IO.fork` interleaves on one event loop. So the sides are two
  processes, `bench/duo.bend` in two modes. `effs/duo.c` shares a mapped
  block with a round counter, ready and done flags, and the GPU's CVs. The
  effects only move words. In memory each process fills its own copy; with
  files each side would load only its share.
- **The CPU pool deals a task to one core for good.** A spine that forks at
  every node, where one side owns nothing, idled the cores dealt to that
  side: the CPU's 1/4 took ~100 ms, against 36 ms for the whole input. The
  CPU side walks the spine in order (`spine.seq`), so each owned subtree
  forks over the whole pool. The GPU side keeps the forks: its cube regrows
  the frontier every iteration.

Results, 1 GiB in memory (`bench/duo.py`, medians of 10-12 rounds,
digests equal):

| when | GPU alone | CPU alone | 3/4 GPU + 1/4 CPU |
|------|-----------|-----------|-------------------|
| before Decision 1, emulator holding ~12 cores (load ~17) | 12.0 ms | 43.5 ms | **10.1 ms** (CPU share 10.0, GPU share 9.9) |
| after Decision 1, load 22-25 (emulator, a VM, another session's benchmark) | **10.2 ms** | 50.1 ms | 12.1-20.3 ms (plans 2:3, 3:7, 4:13) |

Under the lighter load the split beat the GPU alone by 1.19x. With the
faster GPU tree and a heavier load it lost. The CPU ran at about half its
quiet speed, and the GPU's 3/4 share slowed while the CPU hashed (10-14 ms,
where ~7.7 was expected). Giving the GPU side's thread user-interactive QoS
moved nothing past the noise: its medians swung 12-20 ms between runs. On
a quiet machine (CPU ~27 ms, GPU ~9.4 ms a GiB), the balanced split
predicts ~7 ms. Measuring it needs the machine to ourselves.

`test/split.bend`: the official vectors under 11 plans (198/198), plans
deeper than the input included, GPU leaf levels 0 to 6.

## Addendum: the split by slices (same day)

Re-run with the emulator still holding ~12 cores (load 16-25; the user's
pause did not stop its qemu process). Three findings:

- **The GPU clocks down when idle.** The same bang, hot or after a pause
  (`IO.sleep` between bangs, one process): half of 1 GiB 4.9 ms hot,
  6.6 ms after 100 ms idle, 13.9 ms after 300 ms; the whole GiB 8.4, 9.0
  and 17.1. A split whose CPU side is slow leaves the GPU idle each round,
  which is why the one-thread "GPU share alone" runs above looked worse
  than they are.
- **A spine share costs the GPU as much as the whole input.** Hot, in one
  process, no CPU work: the whole GiB 8.7-9.3 ms, one 512 MiB subtree
  5.2-5.9, but 3/4 (512 + 256 MiB) 8.7-9.9 and 7/8 8.7-11.1. A quarter
  alone (256 MiB on 4096 strided lanes) takes 5.0-7.7 ms. Every lane does
  64 chunks, and with fewer than ~16384 lanes the GPU runs at lane latency,
  not bandwidth. 16- or 4-chunk leaves were worse (more cube iterations:
  3/4 at 10.7-11.6 ms). At 2 GiB too, a 3/4 share (19.4-20.2 ms, while the
  CPU hashed its quarter) is no cheaper than the whole (19.2-20.0).
- **Contention is minor.** A hot whole-GiB bang next to a CPU process
  hashing on 18, 8 or 4 threads: 8.9, 9.1, 8.6 ms against 8.6 alone (a
  half-GiB bang did slow beside 18 threads, 10.9 against 5.3, but not beside
  8 or 4).

So the split now cuts by **slices** (`split.bend`: `slice.g`, `slice.c`,
`slice.root`). A whole input of 2^(k+6) chunks is 16 slices, each a whole
subtree. Lane l of 2^k hashes the 4-chunk group l of each of the GPU's first
G slices, so the GPU's share is G/16 of the input on all its lanes, one
balanced tree; joins zip the halves' lists of G CVs group for group, as
`GQuad`'s do. The CPU hashes the other slices with `tree8`, and
`slice.root` folds the 16. Plan `0:G` in `bench/duo.py`.

1 GiB in memory, three interleaved passes of 15 rounds, medians, digests
equal (the GPU share is measured while the CPU hashes its own):

| plan | round | CPU share | GPU share |
|------|-------|-----------|-----------|
| GPU alone (`1:3`) | 8.54-8.85 ms | | 8.54-8.84 |
| 12/16 GPU (`0:12`) | 9.49-11.10 | 9.47-11.09 | 7.62-8.59 |
| **13/16 GPU (`0:13`)** | **7.93-8.06** | 6.64-7.72 | 7.84-8.04 |
| 14/16 GPU (`0:14`) | 8.16-8.29 | 5.10-5.27 | 8.15-8.28 |
| 15/16 GPU (`0:15`) | 8.63-8.78 | 2.53-3.30 | 8.62-8.76 |
| spine 3/4 (`2:3`), for comparison | 11.9-16.3 | | |

The CPU + GPU split beats the GPU alone in every pass, by 1.06-1.12x, with
the CPU at about half its quiet speed (CPU alone 57-64 ms a GiB). A quiet
machine should let the CPU take 4-5 slices.

Still the GPU share does not shrink with its bytes: 13/16 of the input
costs 7.9 ms against 8.6 for all of it. Its lanes do 52 chunks instead of
64, and some cost does not scale (the ~0.9 ms per bang, ADR 0006).

`test/split.bend` adds nine slice splits of 64 KiB to 1 MiB (1 to 16 lanes,
G from 1 to 15), each equal to the CPU tree; `bench/duo` matched the CPU's
digest at 4, 8, 64 and 128 MiB and 1 GiB (odd and even lane depths).

**The CPU flag lead, re-run: refuted.** Rebuilt from the same C (baseline,
`-mllvm -enable-post-misched=false`, `-mllvm -misched-prera-direction=bottomup`,
both), five interleaved rounds on one core: 441-450, 437-458, 443-451 and
443-461 ms, the fastest a different build from round to round; four rounds
on all cores: 34.7-41.3 ms, the same. The earlier 3-19% was load.

## The CPU core (measured, not changed)

One-thread 1 GiB: 384 ms (2.8 GB/s) with the machine lighter. A profile puts
90% in one spin (`c8.go` with `compress8` inlined). Per 8-lane compression
its 3136 instructions are 1937 BLAKE3 vector ops (`add.4s` 689, `eor` 464,
`shl` and `usra` 336 each, `rev32` 112). The remaining ~1200 are ~430
vector spills and reloads (`ldr q` 294, `str q` 135) and ~300 to gather the
block's 128 words into lanes. Eight lanes need 16 x 2 registers for the
state alone, so the message words spill. Four NEON pipes would run the 1937
ops in ~485 cycles; a block takes ~750 in the spin (183 ns at ~4.5 GHz,
less the 10% elsewhere). An interleaved sweep of LLVM
scheduler flags found nothing (see the addendum).

## Not pursued

- Two runtimes in one process (two dylibs of the emitted C). One address
  space would let the CPU side read the GPU's heap. But process-wide state
  (signals, stdout, threads) is shared, and a mapped block does the
  coordination as well.
- SME's streaming SVE has `XAR` (xor and rotate on 32-bit lanes), which
  cuts G from 16 to 10 operations. It is C intrinsics, and the hashing
  stays in Bend.
- Content shortcuts (zero chunks, deduplication): forbidden by §7.5's chunk
  counter, by design.

## Ideas for Bend's runtime

- A bang that runs alongside the pool, an asynchronous bang or a second
  cube, would let `split.bend` run in one process with no coordination.
- The stride shows the general rule from ADR 0006. A lane that streams
  should read near its neighbours. A runtime that deals a bang's tasks in
  address order would give every program that for free.
