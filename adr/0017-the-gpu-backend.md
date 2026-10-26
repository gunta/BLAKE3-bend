# ADR 0017: The GPU backend: the native kernels in the library, the crate and the bindings

Date: 2026-10-26
Status: accepted

## Context

ADR 0013 decided that turboblake runs the hand-written Metal and CUDA
kernels of `bend/ref` wherever they measure faster than the CPU engine,
and keeps the CPU + GPU split of ADR 0011 with whichever GPU kernel is
faster. It left the work as "Next": a GPU backend for the C library,
loaded at run time, with a device-buffer entry point first and then spans
of host memory where the split measures faster; the split measured with
native Metal (it had estimated ~5.4 ms a GiB on the M5 Pro) and through
pinned memory on NVIDIA (~8 ms a GiB on the B200); and release builds kept
CPU-only until the native paths pass the same checks as the CPU engine.

## Decision

### One kernel source, loaded at run time

- **The kernels are bend/ref's**, grown to what a library needs: the mode's
  key words and flags (keyed hashing, key derivation), a 64-bit chunk
  counter starting anywhere, a last block that reads only its own bytes (no
  padding past a buffer's end), and a fold width, so a job can stop at whole
  subtrees of any power-of-two size. The reference tools (`b3metal`,
  `b3cuda`, `cpu_test.c`) run the same source; Metal still passes the
  official vectors at K = 1, 4, 16, 64, and 1 GiB is unchanged (5.4-5.6 ms
  against 5.5-5.8, interleaved, the same digest).
- **Nothing is linked.** `bend/lib/turboblake_gpu.c` is plain C: on macOS it
  opens Metal.framework and drives it through the Objective-C runtime
  (`objc_msgSend`, `dlopen`), on Linux it opens `libcuda.so.1` and uses the
  driver API. The Metal source and the CUDA kernels as PTX (sm_75, ISA 6.4,
  compiled by Homebrew LLVM's clang from `b3.cu` and JIT-compiled by the
  driver for the GPU it finds) are embedded by `bend/lib/gen_gpu.sh`. A
  program linking `libblake3.a` needs no new flags, and every binding
  compiles one more C file. Without a GPU, a driver, or with
  `TURBOBLAKE_GPU=0`, `turboblake_gpu()` is 0 and nothing changes. The Metal
  kernels are ready ~40 ms after the first GPU call (144 ms the first time
  on a machine); CUDA's load in ~1 ms once the driver has cached its JIT.
- **The GPU never computes a root.** A job hashes its bytes into the CVs of
  whole subtrees (the two children of a device subtree, or one CV a slice
  of a split), and the CPU merges those few. So the official code finishes
  every mode, every output length and every seek.

### GPU memory

`turboblake_hasher_update_metal(&h, buffer, offset, len)` and
`turboblake_hasher_update_cuda(&h, device_ptr, len, stream)` feed GPU memory
to any hasher, as `blake3_hasher_update` feeds host memory: in every mode,
any number of times, between host updates. They run `blake3.c`'s own update
loop: the GPU hashes each power-of-two subtree into the two CVs the hasher
pushes; the bytes that finish a chunk, and subtrees under 64 KiB, are copied
to the CPU. A shared Metal buffer is host memory the GPU reads, and goes
through the split below. The Rust crate has the same as
`Hasher::update_metal` / `update_cuda` (the loop of `update_with_join`, with
hazmat's input offsets), and the Python binding as
`hasher.update_cuda(tensor.data_ptr(), nbytes)` and `update_metal(...)`,
with the GIL released.

### Host memory the GPU reads, split with the engine

`turboblake_alloc` (Rust: `blake3::gpu::Memory`) gives host memory the GPU
reads in place: a shared Metal buffer on Apple silicon, pinned memory on
NVIDIA; `turboblake_register` makes existing memory such. Plain
`blake3_hasher_update` over it reaches the subtree hook, which cuts each big
subtree into ~32-64 slices: the GPU takes the first ones (read in place on
Metal, copied over PCIe in 64 MiB pieces on CUDA), the Bend engine the rest
at the same time, and the CPU merges their CVs. The share balances the two
sides' rates: the first job with a warm engine measures them, later jobs
move them by a quarter, so both sides finish together under whatever else
runs on the machine and one noisy job moves the share little.

- The split starts where it beats the engine alone: 16 MiB on Metal, 64 MiB
  on CUDA, whose link may be slow (an L4's split loses at 16 MiB).
- The hook loads the backend only for memory the GPU was given (or under
  `TURBOBLAKE_GPU=all`): every other caller keeps exactly the CPU path of
  ADR 0016, so turboblake stays never slower than b3sum.
- On Apple silicon the split pays only when the engine reads its slices in
  place (ADR 0016's window): without it the engine copies them, the copies
  spend the memory bandwidth the GPU runs on, and 1 GiB took 6.6 ms split
  against 5.6 on the GPU alone. So when the engine would copy, the GPU takes
  it all.
- Subtrees past 2^32 chunks (4 TiB) go to the GPU alone: its kernels count
  chunks in 64 bits.
- The command line stays on the CPU (ADR 0006: wiring a fresh mapping for
  the GPU costs more than the CPU's whole run): its release binaries are
  built without the backend (`TURBOBLAKE_NO_GPU`).

## Results

`bench/duo.py --native` hashes one input (mem.bend's words) through
`blake3.h`: the engine alone from ordinary memory, the GPU alone from its
own memory, the split from memory the GPU reads, and the GPU alone from that
memory. Plans run interleaved, in processes of 12-16 rounds; medians, the
first round of each process left out; every side gives the same digest.
results.json's `gpu_library` holds the tables (`bend/bench/collect.py`, from
`results/gpu-lib-m5pro.json` and `results/modal-lib-B200.json`).

### Apple M5 Pro (18 cores, 20-core GPU, one memory)

At a load average near 6 (Spotlight's indexers):

| input | engine alone | GPU memory | CPU + GPU split | GPU from that memory |
|---|---:|---:|---:|---:|
| 16 MiB | 0.684 ms | 0.750 ms | **0.530 ms** | 0.692 ms |
| 64 MiB | 1.93 ms | 0.900 ms | **0.739 ms** | 0.868 ms |
| 256 MiB | 7.52 ms | 1.77 ms | 1.77 ms | **1.70 ms** |
| 1 GiB | 33.1 ms | 5.85 ms | **5.25 ms (205 GB/s)** | 5.68 ms |

- The split measures **5.25 ms a GiB** (5.08 in an earlier run at a load
  of 5-7), against ADR 0013's estimate of ~5.4: 1.11x the GPU alone, 6.3x
  the engine alone. Fixed shares around the balance lose to the measured
  one (0.85: 5.55 ms, 0.9: 5.70, 1.0: 5.68, 0.8: 6.71).
- At 256 MiB the split ties the GPU alone; under 16 MiB the engine alone
  wins (8 MiB: 0.375 ms against 0.414 split, 0.476 on the GPU), so that is
  where the split starts.
- With the engine reading in place, its side and the GPU's finish together
  (1 GiB: the GPU's 54-55 of 64 slices in 4.7-4.9 ms, the engine's rest in
  4.4-5.1).
- The device path runs the kernel at the speed of `bend/ref`'s own host:
  5.6-5.85 ms against 5.4-5.6 for `b3metal`.

### NVIDIA B200 (Modal, 16 x86 cores, PCIe 5 x16)

| input | engine alone | GPU memory | CPU + GPU split (pinned) | GPU from pinned memory |
|---|---:|---:|---:|---:|
| 16 MiB | 0.573 ms | 0.148 ms | **0.404 ms** | 0.461 ms |
| 64 MiB | 1.08 ms | 0.155 ms | **0.933 ms** | 1.37 ms |
| 256 MiB | 3.54 ms | 0.254 ms | **2.58 ms** | 5.40 ms |
| 1 GiB | 17.7 ms | **0.686 ms** | **11.1 ms** | 21.5 ms |

- **GPU memory: 1 GiB in 0.686 ms (1.57 TB/s)** through
  `turboblake_hasher_update_cuda`, the same as `bend/ref`'s own `b3cuda`
  host (0.69 ms) and ADR 0013's 0.683: the library's work around the kernel
  costs nothing measurable at this size.
- **Pinned host memory: 1 GiB in 11.1 ms** (best round 9.46), 1.59x the
  engine alone, against ADR 0013's estimate of ~8 ms. The link moves
  1 GiB in 21.5 ms (50 GB/s), slower than the 16 cores hash it, so the GPU
  takes ~40% and the rest of the gain the estimate assumed is not there:
  the DMA and the cores read the same host memory, and Modal's shared host
  is noisy (the engine alone ranged 14.6-22.3 ms a GiB across runs).
- An L4 (the smoke test's machine, PCIe at ~12 GB/s under Modal's sandbox)
  shows a slow link's limit: its split wins 1.14x at 64 MiB (1.81 ms
  against 2.06) and 1.23x at 256 MiB (6.24 against 7.65), and loses at
  16 MiB (0.81 against 0.72), so CUDA's split starts at 64 MiB.

### The gates

The native paths run the official checks in the same runs as every other
path:

- `bend/lib/test.py`: every official vector in all three modes, extended
  output and a seek, under several update splits, then random inputs
  against the official `b3sum`, through the engine and through each GPU
  path: GPU memory at an odd offset with host updates between, a shared
  Metal buffer, `turboblake_alloc`'s memory, and host memory under
  `TURBOBLAKE_GPU=all` (the GPU takes every subtree of 2+ chunks), alone
  and split with the engine. 5270/5270 on the M5 Pro (Metal), 4294/4294 on
  an L4 (CUDA); 5366/5366 with `--big` on the M5 Pro (inputs to 3 GiB + 7).
- Upstream's Rust tests, with the engine taking every subtree of 2+ chunks:
  48/48 on the M5 Pro with the GPU taking them too, alone and split with
  the engine (`test_compare_reference_impl` alone runs 291 splits), with
  `gpu.rs`'s own tests (every vector, all modes, through GPU memory between
  host updates; random inputs; hazmat offsets up to 2^52 + 1 GiB); the
  crate's CLI and doc tests pass. On the L4 56/57 in each mode: the one
  failure is upstream's `io::test::test_unmappable_linux`, which fails for
  upstream's crate in Modal's sandbox too (ADR 0018).
- The bindings' own tests under `TURBOBLAKE_GPU=all`: Python 29/29
  (blake3-py's 28 and `tests/test_gpu.py`; 590 GPU subtrees), Node 2165
  checks (5432), Go (307).
- `bend/prove.sh` prints ALL PROOFS CHECK: no Bend code changed; the
  engine and the proven tree are the CPU side of every split.

## Consequences

- The library, the crate and the bindings carry the backend, inert until a
  program hands the GPU memory (GPU memory, `turboblake_alloc`'d or
  registered host memory) or sets `TURBOBLAKE_GPU=all`. The command line's
  release binaries stay CPU-only.
- The kernels in `bend/ref` are shipped code now: a change there runs
  `bend/lib/gen_gpu.sh` and the GPU passes of the tests above, on a Mac
  and on a Modal L4 (`modal run bend/bench/modal_gpu.py --lib-only --gpu L4
  --steps test`).
- The Mac's numbers were taken under load (see ADR 0011's remeasure note):
  the split's balance follows the load by itself, but the table's absolute
  numbers should be taken again on a quiet machine.
- Not done: the site does not draw `results.json`'s new `gpu_library`
  section yet; Node and Go reach the hook but not GPU memory (they have no
  common device-pointer type); a CUDA split from memory that is not pinned
  (the copies would run at half speed and hold the calling thread) stays on
  the CPU; one GPU per process.
