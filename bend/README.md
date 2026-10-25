# BLAKE3 in Bend2

A BLAKE3 implementation written in [Bend2](https://bend-lang.com) (2.0.39),
plus a `b3sum` that prints exactly what the official one prints. Every
compression runs in Bend: the CPU path is an 8-lane `compress8` that clang
packs into NEON registers, the GPU path (`hash1!`) one chunk per lane. C
appears only in the effects that move bytes in and out (`effs/`).

## Layout

| path                    | what                                                  |
|-------------------------|-------------------------------------------------------|
| `blake3.bend`           | the hash: compress, compress8, the trees, entry points (generated) |
| `tools/gen_blake3.py`   | generates `blake3.bend` (unrolled rounds and loaders)  |
| `b3sum.bend`            | the CLI                                               |
| `b3io.bend`, `effs/`    | `B3IO.load` (parallel, mmap) and `B3IO.emit` effects  |
| `build.sh`              | bend -> C -> clang with the tuned flags (ADR 0002)    |
| `test/`                 | official test vectors (both paths), big-file test     |
| `bench/`                | in-memory bench, file bench, race vs b3sum, Rust ref  |
| `../adr/`               | what we did for speed, and what we measured           |

## Build and check

```bash
bend/build.sh bend/b3sum.bend bend/build/b3sum
```

```bash
bend/build.sh bend/test/vectors.bend && bend/test/build/vectors | python3 bend/test/check.py
```

```bash
python3 bend/test/big.py
```

```bash
python3 bend/bench/race.py 15
```

`build.sh` needs `~/.bend/bin/bend` and Apple clang. The official `b3sum`
for comparison: `cargo build --release --features neon` in `../b3sum`.

## Scoreboard (Apple M5 Pro, 6 Super + 12 Performance cores, 20-core GPU)

In memory, warm, same data and digest (`bench/mem.bend` vs `bench/rust`, the
official `blake3` crate with NEON + rayon):

| input          | Rust blake3 NEON | Bend CPU      | Bend GPU (`hash1!`)   |
|----------------|------------------|---------------|-----------------------|
| 1 GiB, 1 core  | 448 ms           | **377 ms**    |                       |
| 16 MiB, all    | 1.13 ms          | **0.50 ms**   | 0.88 ms               |
| 64 MiB, all    | 1.95 ms          | 1.74 ms       | **1.21 ms**           |
| 256 MiB, all   | 6.9 ms           | 6.3-7.1 ms    | **2.43 ms (110 GB/s)**|
| 1 GiB, all     | 27.3-28.4 ms     | 25.9-28.1 ms  | **11.6 ms (93 GB/s)** |

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

Big single files sit on two floors that `b3sum` shares: ~15 ms of page
faults per GiB of a mapped file, and an all-core compute ceiling near
38 GB/s. Small files sit on the kernel's open() floor (ADR 0003). The GPU
is the fastest path for warm in-memory hashing, but its Metal heap costs
~50 ms per GiB to set up, so the one-shot CLI stays on the CPU (ADR 0004).
