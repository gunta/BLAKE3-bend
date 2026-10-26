# ADR 0013: Native GPU kernels where they measure faster, and the split with them

Date: 2026-10-26
Status: accepted (the direction; the command line and the library do not run the GPU yet)

## Context

turboblake's command line and library hash with Bend's tree on the CPU
(ADR 0003, ADR 0012). The repository has two GPU paths for the same tree:

- **Bend's own** (`hash1!`): Metal on the Mac (ADR 0004, 0005, 0011) and CUDA
  on NVIDIA (Bend's runtime on Modal, `bench/modal_gpu.py`).
- **Hand-written** CUDA and Metal in `bend/ref` (ADR 0006), kept until now as
  yardsticks only: the rule was that the hashing stays in Bend and native
  code only shows how far Bend is from the hardware.

The user changed that rule: the shipped command line and library do not have
to be Bend only. They use Metal or CUDA where it makes sense, and keep the
CPU + GPU split of ADR 0011 with whichever GPU kernel is faster.

To show what is at stake, SHA-256 is now measured beside the GPU runs, on
the same machines (`bench/modal_sha.py` on the B200 host; the language runs
of ADR 0012 on the Mac). One 1 GiB buffer in memory, medians, the same
digest from every BLAKE3, in ms (results.json `versus`):

| machine | SHA-256 | BLAKE3, one core | BLAKE3, every core | turboblake, CPU | Bend on the GPU | native GPU kernel |
|---|---|---|---|---|---|---|
| NVIDIA B200 (Modal, 16 x86 cores) | 574 | 193 | 13.9 | 15.3 | 3.20 | **0.683** |
| Apple M5 Pro (18 cores, 20-core GPU) | 335 | 448 | 27.8 | 26.9 | 9.43 | **6.69** |

- SHA-256 is OpenSSL with the CPU's SHA instructions: 3.0.16 with SHA-NI on
  the B200 host (Python's hashlib, 1.87 GB/s), Node's crypto on the Mac (the
  fastest of the four languages' SHA-256 there, 3.2 GB/s). It chains every
  block to the one before, so one input gets one core.
- On one core SHA-256 and BLAKE3 trade places: with ARMv8's SHA-2
  instructions the Mac runs SHA-256 1.3x faster than BLAKE3; on the B200
  host's AVX-512 cores BLAKE3 is 3.0x faster. BLAKE3's lead is the tree.
- The native CUDA kernel hashes 1 GiB in 0.683 ms (1.57 TB/s; 2 GiB in
  1.283 ms, 1.67 TB/s): 841x SHA-256, 20x the official crate on all 16
  cores, 4.7x Bend's CUDA path. On the B200 the GPU sides read the buffer
  from the GPU's own memory; the first run, which moves it there through
  CUDA managed memory, is left out.
- Native Metal is 1.4x Bend's Metal path at 1 GiB (6.69 against 9.43 ms):
  50x SHA-256, 4.2x the official crate on all 18 cores.

## Decision

Each target runs the fastest kernel measured for it, and the split pairs the
fastest CPU side with the fastest GPU side.

- **Bend stays the CPU engine** and the tree the laws are about
  (LAWS.bend, PROOF.bend). A native kernel is BLAKE3 only if it gives the
  official vectors and the CPU tree's digest on random inputs, in the same
  test runs as every other path.
- **Data already in GPU memory** (CUDA device buffers, Metal buffers): the
  native kernel. This is where the GPU wins most and needs nothing from the
  host: model weights and checkpoints that live on the GPU.
- **Host data on Apple silicon**: the split of ADR 0011 with native Metal on
  the GPU side instead of Bend's, for long-running processes (the daemon,
  the library inside a server). Ideal balance from the table: ~200 GB/s, 1 GiB
  in ~5.4 ms against 6.69 for the GPU alone; to be measured. A one-shot
  `turboblake` on a file stays on the CPU: wiring a fresh mapping for the GPU
  costs ~37 ms a GiB (ADR 0006), more than the CPU's whole run.
- **Host data on NVIDIA**: the bytes cross the host link, which on a PCIe 5
  x16 host moves 1 GiB in about the time the 16 cores hash it. A split that
  keeps every core hashing and streams the rest to the GPU could reach
  ~130 GB/s (1 GiB in ~8 ms against 13.9 on the CPU); to be measured.
- **The site** shows the native kernels as turboblake's, labeled "native GPU
  kernel", with a note that the command line and the library do not run
  them yet.

## Consequences

- Next: a GPU backend for libblake3-bend, loaded at run time (Metal.framework,
  `libcuda` through the driver API with the kernel shipped as PTX), so a
  machine without a GPU, or a build without the backend, keeps the CPU engine.
  It takes a device-buffer entry point first, then spans of host memory where
  the split measures faster than the CPU alone.
- Next: `bench/duo.py` with native Metal as the GPU side, and a host-memory
  split on the B200 through pinned memory, to replace the estimates above
  with numbers.
- The release builds stay CPU-only until that backend passes the same
  vector and random-input checks as the CPU engine.
- The home page and /benchmarks/ gain "1 GiB, from SHA-256 to the GPU"
  (`site/src/components/Versus.astro`), from results.json `versus`, which
  `bench/collect.py` builds from `modal-B200.json`, `modal-sha-B200.json`
  and the Mac's tables.
