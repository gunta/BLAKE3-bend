# BLAKE3 in Bend2

A BLAKE3 implementation written in [Bend2](https://bend-lang.com) (2.0.39),
plus a `b3sum` that prints exactly what the official one prints. Every
compression runs in Bend: the CPU path is an 8-lane `compress8` that clang
packs into NEON registers, the GPU path (`hash1!`) one chunk per lane. C
appears only in the effects that move bytes in and out (`effs/`).

## Layout

| path                    | what                                                  |
|-------------------------|-------------------------------------------------------|
| `blake3.bend`           | the hash: compress, compress8, the trees (generated; no `@unsafe` def) |
| `hash.bend`             | the entry points that run: the trees with Array.fork   |
| `split.bend`            | one input hashed by the CPU and the GPU at once (ADR 0011) |
| `tools/gen_blake3.py`   | generates `blake3.bend` (unrolled rounds and loaders)  |
| `LAWS.bend`, `PROOF.bend` | the laws and their proofs (`tools/gen_laws.py`); `prove.sh` is the gate |
| `b3sum.bend`            | the CLI                                               |
| `b3io.bend`, `effs/`    | `B3IO.load` (parallel, mmap) and `B3IO.emit` effects  |
| `stack.bend`            | a streamed file's merge stack, apart from the reads so the laws can name it |
| `build.sh`              | bend -> C -> clang with the tuned flags (ADR 0002)    |
| `test/`                 | official test vectors (both paths), big-file test     |
| `bench/`                | in-memory bench, file bench, race vs b3sum, Rust ref; `duo` (CPU + GPU), `gpusum` |
| `ref/`                  | native Metal and CUDA BLAKE3, the GPU path's yardstick (ADR 0006) |
| `../adr/`               | what we did for speed, and what we measured           |

## Build and check

```bash
bend/build.sh bend/b3sum.bend bend/build/b3sum
```

```bash
bend/build.sh bend/test/vectors.bend && bend/test/build/vectors | python3 bend/test/check.py
```

```bash
bend/build.sh bend/test/split.bend && bend/test/build/split | python3 bend/test/check.py
```

```bash
python3 bend/test/big.py
```

```bash
python3 bend/bench/race.py 15
```

`build.sh` needs `~/.bend/bin/bend` and Apple clang. The official `b3sum`
for comparison: `cargo build --release --features neon` in `../b3sum`.

## Laws

`LAWS.bend` states what the code must satisfy and `PROOF.bend` proves it
(ADRs 0007, 0010, 0014 and 0015): 41 laws, 412 lemmas. The gate, about four
minutes, most of it the checker computing BLAKE3 itself:

```bash
bend/prove.sh
```

It prints ALL PROOFS CHECK when every law holds:

- **Known answers**: official vectors through the CPU tree (`hash`, 0 to
  8193 bytes, Leaf8 included), the GPU tree (`hash1`), the GPU flat leaf
  `g4`, and two spans merged as b3sum merges a big file's parts.
- **The 8-lane path, for every input**: each lane of `compress8` and
  `par8` is the scalar `compress` or `parent` of that lane; `perm` gives the
  C code's `MSG_SCHEDULE`. The IV and flags are the C code's too.
- **The trees that run, for every input**: the CPU's 8-lane tree
  (`hash.at`, `hash`), the GPU's tree (`hash1.at`, `hash1`: flat leaves and
  strided lanes) and the keyed tree (`hash8.at.k`, keyed hashing and key
  derivation) give blake3.bend's scalar tree's CV for every array and span,
  both words of its chunk counter included (and every key and mode flag),
  and that tree is BLAKE3's: the left-full binary
  tree over the chunks, each leaf a chunk and each node a parent.
- **Outboards, for every input**: the tree that writes iroh's bao outboard
  (`hash.ob`, `hash.ob.at`) gives the plain tree's CV for every array,
  length and span.
- **Tree shapes, for any compression function**: BLAKE3's tree splits into
  its 2^k-chunk segments (what b3sum's 1 GiB parts rely on), and a
  level-by-level reduction (pair neighbours, carry the odd one) builds the
  same tree, with n leaves and n - 1 parents for n chunks; `tree1`'s split
  rule is the digit form for every chunk count.
- **Streaming, for any segment count**: the loop b3io runs on a streamed
  file (`stack.bend`'s `stk.go`, its reads a template) answers BLAKE3's
  tree over the segments' CVs, ROOT on the top parent, for every CV the
  reads answer; its lazy merge stack builds that tree, every segment once
  and in order.

`python3 bend/tools/gen_laws.py` regenerates both files.

## Scoreboard (Apple M5 Pro, 6 Super + 12 Performance cores, 20-core GPU)

In memory, warm, same data and digest (`bench/mem.bend` vs `bench/rust`, the
official `blake3` crate with NEON + rayon):

| input          | Rust blake3 NEON | Bend CPU      | Bend GPU (`hash1!`)   |
|----------------|------------------|---------------|-----------------------|
| 1 GiB, 1 core  | 448 ms           | **377 ms**    |                       |
| 16 MiB, all    | 1.13 ms          | **0.50 ms**   | 0.88 ms               |
| 64 MiB, all    | 1.95 ms          | 1.74 ms       | **1.21 ms**           |
| 256 MiB, all   | 6.9 ms           | 6.3-7.1 ms    | **2.43 ms (110 GB/s)**|
| 1 GiB, all     | 27.3-28.4 ms     | 25.9-28.1 ms  | **9.4 ms (114 GB/s)** |

End to end, `b3sum FILE...` vs the official `b3sum` 1.8.7 (15 interleaved
rounds, medians, `bench/race.py`; output byte-identical):

| workload                   | b3sum    | Bend b3sum | result        |
|----------------------------|----------|------------|---------------|
| 1 GiB file                 | 49.8 ms  | 48.4 ms    | 1.03x faster  |
| 64 MiB file                | 7.4 ms   | 7.3 ms     | 1.01x faster  |
| 5 GiB file                 | 249.4 ms | 242.0 ms   | 1.03x faster  |
| 10k x 4 KiB                | 148.5 ms | 77.1 ms    | 1.93x faster  |
| 2k x 64 KiB                | 275.4 ms | 25.7 ms    | 10.70x faster |
| 1k x 1 MiB                 | 241.7 ms | 70.6 ms    | 3.42x faster  |
| SDK headers (3460 files)   | 129.1 ms | 37.5 ms    | 3.45x faster  |
| cargo sources (8000 files) | 259.5 ms | 73.5 ms    | 3.53x faster  |

The CPU and the GPU can share one input (`split.bend`, two processes,
ADR 0011): with 13 of 16 slices on the GPU, 1 GiB takes 7.93-8.06 ms
against 8.54-8.85 for the GPU alone in the same runs (`bench/duo.py`).

Hand-written Metal (`ref/`, ADR 0006) hashes the same 1 GiB in 6-6.7 ms,
and 256 MiB in 1.7-1.9 ms. The GPU hash is bound by reads, in Bend too (its
compressions alone run at native speed). Past 512 MiB, Bend's lanes read
interleaved 16-chunk groups, so the lanes running together read neighbouring
memory (ADR 0011: 1 GiB 13.2 -> 9.4 ms, as fast as the native kernel in
Bend's old lane shape); what is left is ~1.3x in its array reads and
~0.9 ms per bang below 64 MiB.

Big single files sit on two floors that `b3sum` shares: ~15 ms of page
faults per GiB of a mapped file, and an all-core compute ceiling near
38 GB/s. Small files sit on the kernel's open() floor (ADR 0003). The GPU
is the fastest path for warm in-memory hashing, but its Metal heap costs
~50 ms per GiB to set up, so the one-shot CLI stays on the CPU (ADR 0004).
