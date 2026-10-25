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

In memory, warm, same data and digest (`bench/mem.bend` vs `bench/rust`):

| input          | Rust blake3 NEON | Bend CPU      | Bend GPU (`hash1!`) |
|----------------|------------------|---------------|---------------------|
| 1 GiB, 1 core  | 448 ms           | **377 ms**    |                     |
| 16 MiB, all    | 1.13 ms          | **0.50 ms**   |                     |
| 64 MiB, all    | 1.95 ms          | **1.74 ms**   | 1.2 ms              |
| 256 MiB, all   | 6.9 ms           | 6.3-7.1 ms    | 2.6-3.8 ms          |
| 1 GiB, all     | 27.3-28.4 ms     | 25.9-28.1 ms  | **12.7 ms**         |

End to end, `b3sum FILE...` vs the official `b3sum` (interleaved medians,
`bench/race.py`):

| workload        | b3sum    | Bend b3sum | result       |
|-----------------|----------|------------|--------------|
| 10k x 4 KiB     | 150.6 ms | 77.3 ms    | 1.95x faster |
| 2k x 64 KiB     | 285.9 ms | 28.4 ms    | 10.1x faster |
| 64 MiB file     | 6.8 ms   | 6.8 ms     | tie          |
| 1 GiB file      | 47.2 ms  | 46.3 ms    | 1.02x faster |
| 5 GiB file      | 231.0 ms | 226.9 ms   | 1.02x faster |

Big single files sit on two floors that `b3sum` shares: ~15 ms of page
faults per GiB of a mapped file, and an all-core compute ceiling near
38 GB/s. Small files sit on the kernel's open() floor (ADR 0003).
