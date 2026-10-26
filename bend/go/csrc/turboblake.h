// libturboblake: the official BLAKE3 C API (blake3.h), with big subtrees
// hashed by the Bend engine, and the GPU where it measures faster. These
// calls are the only additions.
#ifndef TURBOBLAKE_H
#define TURBOBLAKE_H

#include <stddef.h>
#include <stdint.h>

#include "blake3.h"

#ifdef __cplusplus
extern "C" {
#endif

// The two CVs of a complete subtree of input_len bytes (a power of two of
// 2+ chunks), hashed by the engine; 0 when the C library should hash it.
// blake3.c calls this; callers of blake3.h never need to.
int turboblake_subtree(const uint8_t *input, size_t input_len, const uint32_t key[8],
                        uint64_t chunk_counter, uint8_t flags, uint8_t out[64]);

// 1 once the engine has started (it starts on the first big update).
int turboblake_running(void);

// The GPU (ADR 0017)
// ------------------
// The native Metal and CUDA kernels, loaded at run time (Metal.framework on
// macOS, libcuda's driver API elsewhere). Without a GPU or a driver, in a
// build without the backend, or with TURBOBLAKE_GPU=0, these answer 0 (or
// NULL) and nothing else changes.

#define TURBOBLAKE_GPU_METAL 1
#define TURBOBLAKE_GPU_CUDA 2

// TURBOBLAKE_GPU_METAL or TURBOBLAKE_GPU_CUDA once the backend loads, else 0.
int turboblake_gpu(void);

// Feeds len bytes of GPU memory to self, as blake3_hasher_update feeds host
// memory: any hasher (plain, keyed, derive-key), any number of updates
// between host ones, then finalize as usual. 1 on success; 0 when the
// backend cannot read it, with self unchanged.
//   Metal: an id<MTLBuffer> (as void *) from offset. A shared buffer is host
//          memory the GPU reads, split between the CPU and the GPU like
//          turboblake_alloc's; a private one is hashed on the GPU.
//   CUDA:  a device pointer, in the context it belongs to, on stream (a
//          CUstream; NULL for the default stream), after the work queued
//          there. The call returns when the hash is done.
int turboblake_hasher_update_metal(blake3_hasher *self, void *buffer, size_t offset, size_t len);
int turboblake_hasher_update_cuda(blake3_hasher *self, uint64_t device_ptr, size_t len,
                                  void *stream);

// Host memory the GPU reads in place: a shared Metal buffer on Apple
// silicon, pinned memory on NVIDIA. blake3_hasher_update over it splits
// big subtrees between the CPU (the engine) and the GPU, at the share their
// measured rates balance. turboblake_alloc is NULL without a GPU (use
// malloc then); turboblake_register(p, len) makes existing memory such
// (page-aligned on macOS), until turboblake_unregister(p).
void *turboblake_alloc(size_t len);
void turboblake_free(void *p);
int turboblake_register(void *p, size_t len);
void turboblake_unregister(void *p);

#ifdef __cplusplus
}
#endif

#endif
