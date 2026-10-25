# Native GPU references

Hand-written Metal and CUDA BLAKE3, to race Bend's GPU path (`hash1!`)
against and to find out where it loses. They are yardsticks: the hashing in
`b3sum` stays in Bend. What we measured with them is in
[ADR 0006](../../adr/0006-native-gpu-references.md).

| path                 | what                                                     |
|----------------------|----------------------------------------------------------|
| `b3core.h`           | the compression: one header for Metal, CUDA and C        |
| `metal/b3.metal`     | kernels: `leaf`, `merge`, and the rooflines `roof_*`     |
| `metal/b3metal.m`    | host: vectors, in-memory runs, files, rooflines          |
| `cuda/b3.cu`         | the same kernels for NVIDIA                              |
| `cuda/b3cuda.cu`     | host                                                     |
| `cpu_test.c`         | the kernels' tree logic on the CPU, against the vectors  |
| `race_gpu.py`        | Bend `bench/mem` (GPU) against the Metal reference       |
| `bend/roof.bend`     | Bend's rooflines: `hash1!`'s tree with read-only or compute-only leaves |
| `bend/cube.sh`       | builds a Bend program with a bigger GPU lane cube (patched C) |

## How it hashes

A `leaf` thread hashes K consecutive chunks and folds them with a CV stack,
as the reference implementation does; the 32 lanes of a SIMD group (a CUDA
warp) then fold their CVs with shuffles, one CV per 32K chunks. `merge`
repeats the SIMD fold, one CV per thread, until one node is left. Pairing a
level's nodes and carrying an odd one up builds BLAKE3's left-full tree, so
each dispatch knows whether its last merge is the root. K = 0 picks Bend's
leaf size (`level` in `blake3.bend`), to run the native kernel in
`hash1!`'s shape.

## Run

```bash
bend/ref/metal/build.sh && bend/ref/metal/build/b3metal vectors 4 | python3 bend/test/check.py
```

```bash
bend/build.sh bend/bench/mem.bend && python3 bend/ref/race_gpu.py 5
```

```bash
bend/ref/metal/build/b3metal mem 28 10 4
```

```bash
bend/ref/metal/build/b3metal roof 28 10 64
```

`mem <d> <reps> [K] [threadgroup]` hashes 2^d words of `bench/mem.bend`'s
data; `file <path> <reps> [K]` maps a file and wraps it with no copy;
`roof <d> <reps> [K]` times the reads alone (`read`, per-thread contiguous;
`stride`, interleaved over threads; `redir`, through a redirect cell) and
the compressions alone (`alu`). Environment: `B3_W=1|2|4` chunks
interleaved per leaf thread, `B3_LOAD=wide|scalar|coherent|coherent-scalar`
for the leaf's loads, `B3_CALL=1` for chunk compressions as calls.

CUDA, on a machine with CUDA 12+:

```bash
bend/ref/cuda/build.sh && bend/ref/cuda/build/b3cuda vectors 4 | python3 bend/test/check.py
```

Without one, `bend/ref/cuda/build.sh --ptx` compiles the kernels to PTX
with Homebrew LLVM's clang, and `cpu_test.c` checks their logic:

```bash
mkdir -p bend/ref/build && cc -O2 -o bend/ref/build/cpu_test bend/ref/cpu_test.c && bend/ref/build/cpu_test | python3 bend/test/check.py
```
