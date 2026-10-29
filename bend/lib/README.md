# libturboblake

The official BLAKE3 C library (`c/` in this repository, `blake3.h`
unchanged), with one change: when an update reaches a big complete subtree,
the part BLAKE3 can hash in parallel, the subtree goes to a Bend2 engine
that hashes it on every core. Everything else is upstream's code: the
chunk state, the CV stack, keyed hashing and key derivation, finalization,
extended output. Programs written against `blake3.h` relink and run
unchanged; same symbols, same `blake3_hasher` layout.

```bash
brew install gunta/tap/libturboblake
```

or a `libturboblake` archive from the
[releases](https://github.com/gunta/turboblake/releases) (macOS and Linux,
arm64 and x86-64), or from source with CMake:

```bash
cmake -S bend/lib -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build && cmake --install build --prefix /usr/local
```

Each installs `include/turboblake/blake3.h` (upstream's header) and
`turboblake.h`, `libturboblake` (static and shared), a pkg-config file and
a CMake package, so a program keeps `#include "blake3.h"` and links one of:

```bash
cc app.c $(pkg-config --cflags --libs libturboblake) -o app
```

```cmake
find_package(turboblake REQUIRED)
target_link_libraries(app turboblake::turboblake)
```

The engine needs clang on a POSIX system; elsewhere (Windows, gcc) CMake
builds the official C alone. `-DTURBOBLAKE_TARGET_CPU=native` tunes the
engine for this machine instead of each platform's release baseline.
`bend/lib/build.sh` is the quick build for working on it here: `build/`
gets `libblake3.a` and `libblake3.{dylib,so}` (also as `libturboblake`),
`include/blake3.h`, and `bin/blake3` (a test CLI):

```bash
cc -I bend/lib/build/include app.c bend/lib/build/lib/libblake3.a -lpthread -o app
```

## How it works

- `blake3.c`'s `compress_subtree_to_parent_node` asks `turboblake_subtree`
  (`turboblake.c`) first. That cuts the subtree into spans of at most
  1 GiB, each a whole subtree, hands them to the engine in one job, and
  merges their CVs into the two child CVs upstream expects.
- The engine (`engine.bend`, `engine.c`) is a Bend program that runs on a
  thread of its own for the life of the process: `Eng.next` waits for a
  job, Bend hashes every span at once (`H.hash.at`, the 8-lane tree),
  `Eng.done` hands the CVs back.
- Bend's arrays live in an 8 TiB window past its heap's base. On Linux the
  engine puts that window over the region where `mmap` (and so `malloc`)
  places big buffers, and reads the caller's memory where it lies: no
  copy. On macOS big allocations come from the bottom of a zone above a
  384 GiB guard, so the library reserves the heap's room there when it
  loads (and fills the holes below it with placeholders): buffers the
  program allocates afterwards lie in the window too (ADR 0016). Anything
  outside it is copied (by a few helper threads) into two warm heap blocks.
- The engine starts on the first big update. Before that, and for small
  subtrees, keyed hashing and key derivation (for now), and in a forked
  child, the official C code hashes as it always does.
- The smallest subtree worth a trip to the engine is calibrated once: the
  engine's fixed cost per job against the C code's one-thread rate.
- The library build patches Bend's emitted C (`patch.py`) so it can live
  inside another program: no process-wide signal handlers.

Environment: `TURBOBLAKE=0` turns the engine off, `TURBOBLAKE_MIN=<bytes>`
sets the threshold, `TURBOBLAKE_THREADS=<n>` caps the engine's threads,
`TURBOBLAKE_TRACE=1` prints the calibration and the jobs.

## The GPU

`turboblake_gpu.c` runs the hand-written Metal and CUDA kernels of
`bend/ref` from the library (ADR 0017). It links nothing: Metal is reached
through the Objective-C runtime and Metal.framework, opened at run time,
and CUDA through libcuda's driver API, with the kernels shipped as PTX
(`gen_gpu.sh` embeds both in `csrc/turboblake_kernels.h`). A machine
without a GPU or a driver keeps the CPU engine, unchanged; `GPU=0
bend/lib/build.sh` builds without the backend. The calls (`turboblake.h`):

```c
blake3_hasher h;
blake3_hasher_init(&h);
turboblake_hasher_update_metal(&h, (void *)mtl_buffer, offset, len);    // an id<MTLBuffer>
turboblake_hasher_update_cuda(&h, device_ptr, len, stream);             // CUDA device memory
blake3_hasher_finalize(&h, out, 32);

uint8_t *p = turboblake_alloc(len);   // host memory the GPU reads in place
blake3_hasher_update(&h, p, len);     // big subtrees split between the CPU and the GPU
```

- GPU memory is hashed where it is, in any mode and between host updates:
  the GPU hashes each subtree into the two CVs `blake3.c` pushes, and the
  few bytes that finish a chunk come to the CPU. 1 GiB in 5.85 ms on the
  M5 Pro's GPU, 0.686 ms on a B200 (ADR 0017).
- Host memory from `turboblake_alloc` (a shared Metal buffer, CUDA pinned
  memory) or `turboblake_register` splits each subtree from 16 MiB (Metal)
  or 64 MiB (CUDA) between the engine (the last slices) and the GPU (the
  first), at the share their measured rates balance: 1 GiB in 5.3 ms on
  the M5 Pro against 33 ms on the CPU alone, 11.1 ms on a B200's host
  against 17.7. Other memory never goes to the GPU.

Environment: `TURBOBLAKE_GPU=0` turns it off, `TURBOBLAKE_GPU_MIN=<bytes>`
sets the smallest subtree for it, `TURBOBLAKE_GPU_SHARE=<0..1>` fixes its
share of a split, `TURBOBLAKE_GPU=all` gives it every subtree (copied to it
if need be: the tests run the official checks through the kernels that
way), `TURBOBLAKE_GPU_DEVICE=<i>` picks the CUDA device for host memory.

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
2 GiB + 1 against the official `b3sum`. With a GPU backend it runs them
through the GPU too: the input in GPU memory (at an odd offset, between
host updates), in a shared Metal buffer, and host memory under
`TURBOBLAKE_GPU=all`, alone and split with the engine. `bench.py` hashes one in-memory
buffer per size through the same `blake3.h`, against the official C
library (SIMD, one thread: it has no threads of its own without TBB).

| one update, in memory | official C | libturboblake | |
|---|---:|---:|---:|
| 1 MiB, M5 Pro | 0.497 ms | 0.179 ms | 2.8x |
| 64 MiB, M5 Pro | 28.0 ms | 2.83 ms | 9.9x |
| 1 GiB, M5 Pro | 481 ms | 38.7 ms | 12.4x |
| 1 GiB, Linux x86-64 (Modal) | 323 ms | 25.6 ms (no copy) | 12.6x |

(The Mac numbers were taken with other work running at a load average
near 7.)
