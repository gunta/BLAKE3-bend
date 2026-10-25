# b3sum-bend

`b3sum`, written in [Bend2](https://bend-lang.com): a BLAKE3 command line
tool that prints exactly what the official
[`b3sum`](https://crates.io/crates/b3sum) prints, but hashes many files at
once and every big file across all cores.

```bash
cargo install b3sum-bend
```

```bash
b3sum-bend FILE...
```

Needs clang (Apple's, or LLVM clang 19+ on Linux; set `CC` if clang is not
the default). Runs on macOS and Linux, arm64 and x86-64.

## What it is

The BLAKE3 code is Bend2 source (`bend/blake3.bend` in the
[repository](https://github.com/gunta/BLAKE3-bend)): an 8-lane compression
function that clang vectorizes into SIMD registers, the BLAKE3 tree as a
parallel fork tree, and 1 GiB segments for files of any size up to 4 TiB.
Small C effects move bytes in (parallel open, zero-copy `mmap`) and out (one
write). This crate ships the single C file Bend emits for it, so installing
needs no Bend toolchain.

Against the official `b3sum` 1.8.7 on an Apple M5 Pro (medians, output
byte-identical): a 101.5 GB DeepSeek-V4.1 model shard (bigger than RAM) in
7.65 s against 211 s (27.6x: files not in the page cache stream at SSD
speed); 2,000 x 64 KiB files 10.7x faster, 1,000 x 1 MiB 3.4x, 8,000 cargo
source files 3.5x, 10,000 x 4 KiB 1.9x; cached 1 GiB and 5 GiB files 1.03x.
Benchmarks, method and the limits we hit:
[gunta.github.io/BLAKE3-bend](https://gunta.github.io/BLAKE3-bend/).

## Usage

Same as `b3sum` for plain hashing: file names (or none, or `-`, for stdin);
one `<hash>  <name>` line per file; exit status 1 if a file could not be
read. Runtime options go between `+RTS` and `-RTS`, for example
`b3sum-bend +RTS --threads 8 -RTS big.iso`.

## License

CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3. The
bundled `csrc/b3sum.c` contains the Bend2 runtime, Apache-2.0
(github.com/bendlang/bend).
