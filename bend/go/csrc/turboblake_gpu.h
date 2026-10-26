// libturboblake's GPU backend (ADR 0017): the native Metal and CUDA BLAKE3
// kernels of bend/ref, loaded at run time. Internal to the C library
// (turboblake.c) and the Rust crate (gpu.rs); the public calls are in
// turboblake.h.
#ifndef TURBOBLAKE_GPU_H
#define TURBOBLAKE_GPU_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Where a job's bytes are: host memory, a Metal buffer (an id<MTLBuffer>
// and a byte offset), or a CUDA device pointer (with a CUstream, or 0).
enum { TBG_HOST = 0, TBG_METAL = 1, TBG_CUDA = 2 };

// 1 for Metal, 2 for CUDA once the backend has loaded (the first call loads
// it), 0 without one: no GPU, no driver, TURBOBLAKE_GPU=0, a forked child.
int tbg_backend(void);

// The two child CVs of a subtree of 2+ chunks (any length, from chunk
// counter ctr, in the mode of key and flags) in host memory, the way
// turboblake_subtree answers: 1 if the GPU took it, alone or beside the
// Bend engine; 0 if it is not the GPU's (small, memory the GPU does not
// read in place, no backend), and the caller hashes it as before.
int tbg_subtree(const uint8_t *input, uint64_t len, const uint32_t key[8], uint64_t ctr,
                uint8_t flags, uint8_t out[64]);

// The same for a subtree in GPU memory (kind TBG_METAL or TBG_CUDA), on the
// GPU alone: 1 on success.
int tbg_dev_subtree(int kind, void *obj, uint64_t off, uint64_t len, void *stream,
                    const uint32_t key[8], uint64_t ctr, uint8_t flags, uint8_t out[64]);

// The smallest device subtree worth a GPU job (TURBOBLAKE_GPU_MIN if set,
// else 64 KiB): smaller ones are copied to the host and hashed there.
uint64_t tbg_dev_min(void);

// Copies len bytes of GPU memory at off to host memory dst: 1 on success.
int tbg_read(int kind, void *obj, uint64_t off, uint64_t len, void *stream, void *dst);

// A Metal buffer's bytes when the CPU can read them (shared storage), with
// its length; NULL for a GPU-only buffer or without Metal.
void *tbg_metal_contents(void *buffer, uint64_t *len);

// Host memory the GPU reads in place: on Apple silicon a shared Metal
// buffer, on NVIDIA pinned memory, so updates over it can split between
// the CPU and the GPU. tbg_alloc is NULL without a backend.
void *tbg_alloc(size_t len);
void tbg_free(void *p);
int tbg_register(void *p, size_t len);
void tbg_unregister(void *p);
// A Metal buffer's shared bytes as host memory the GPU reads (the update
// over a shared buffer), until the matching tbg_unregister(contents).
int tbg_register_metal(void *buffer);

// For tests: GPU memory holding pad zero bytes, then len bytes of p (on
// Metal a shared buffer, or a private one when gpu_only); NULL without a
// backend. Freed with tbg_drop.
void *tbg_upload(const void *p, uint64_t len, uint64_t pad, int gpu_only);
void tbg_drop(void *obj);

#ifdef __cplusplus
}
#endif

#endif
