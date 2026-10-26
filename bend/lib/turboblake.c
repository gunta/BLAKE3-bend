// libturboblake's one hook into the official C library
// ======================================================
//
// blake3.c (patched by build.sh) asks turboblake_subtree first whenever an
// update reaches a complete power-of-two subtree of 2+ chunks: the work its
// SIMD loop would do on one thread. If the subtree is big enough to beat
// the trip to the engine, it is cut into spans of at most 1 GiB (whole
// subtrees), the Bend engine (engine.bend) hashes every span at once on
// every core, and the span CVs merge here, as parent nodes, into the two
// CVs the C library expects. Anything else (small subtrees, a forked child,
// an engine that failed to start) answers 0 and C hashes it as upstream does.
//
// The GPU backend (turboblake_gpu.c, built with -DTURBOBLAKE_GPU) asks
// first, for memory the GPU was given, and hashes GPU memory itself
// (turboblake_hasher_update_metal/_cuda below).
//
// Environment:
//   TURBOBLAKE=0          never use the engine
//   TURBOBLAKE_MIN=n      smallest subtree in bytes for the engine (default:
//                          calibrated at the first big update)
//   TURBOBLAKE_THREADS=n  the engine's threads (default: every core)
//   TURBOBLAKE_GPU*       the GPU's (turboblake_gpu.c)

#define _GNU_SOURCE  // clock_gettime under -std=c11
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "blake3_impl.h"
#include "turboblake.h"
#ifdef TURBOBLAKE_GPU
#include "turboblake_gpu.h"
#endif

int b3e_hash(uint32_t n, const unsigned char* const* p, const uint64_t* len,
             const uint64_t* cb, unsigned char (*out)[32]);
int b3e_hash_k(uint32_t n, const unsigned char* const* p, const uint64_t* len,
               const uint64_t* cb, const uint32_t* key, uint32_t kf,
               unsigned char (*out)[32]);
const void* b3e_window(void);
int b3e_inside(const void* p, uint64_t len);
// 1 when the engine takes chunk counters past 2^32 (engine.c). Weak: a
// prebuilt engine older than it (a Go module's .syso) has none, and then
// subtrees past 4 TiB stay with the C library.
int b3e_hi(void) __attribute__((weak));

#define SPAN_MAX (1ull << 30)
#define SPAN_COPY (64ull << 20)

// The smallest subtree the engine takes: TURBOBLAKE_MIN if set, else
// calibrated on the first subtree that might qualify. The engine costs a
// fixed O per job (waking its threads; ~0.1 ms on a Mac, more in a
// sandbox) and then runs ~10x the one-thread SIMD rate R, so it wins past
// about O * R bytes; it takes subtrees from twice that.
static size_t bend_fixed(void) {
  static size_t min = 1;
  if (min == 1) {
    const char* off = getenv("TURBOBLAKE");
    const char* m = getenv("TURBOBLAKE_MIN");
    min = off != NULL && !strcmp(off, "0") ? SIZE_MAX
        : m != NULL && atoll(m) >= 2 * BLAKE3_CHUNK_LEN ? (size_t)atoll(m)
        : 0;
  }
  return min;
}

static double now_s(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

#define PROBE (256 * 1024)

static const uint8_t* calib_input;
static size_t calib_min = SIZE_MAX;

static void calibrate(void) {
  double o = 1e9, r = 1e9;
  unsigned char out[1][32];
  const unsigned char* p[1] = { calib_input };
  uint64_t len[1] = { 2 * BLAKE3_CHUNK_LEN }, cb[1] = { 0 };
  for (int i = 0; i < 4; i += 1) {
    double t = now_s();
    if (!b3e_hash(1, p, len, cb, out)) {
      return;  // no engine: calib_min stays SIZE_MAX
    }
    t = now_s() - t;
    o = t < o ? t : o;
  }
  uint8_t cvs[MAX_SIMD_DEGREE_OR_2 * BLAKE3_OUT_LEN];
  for (int i = 0; i < 2; i += 1) {
    double t = now_s();
    blake3_compress_subtree_wide(calib_input, PROBE, IV, 0, 0, cvs, false);
    t = now_s() - t;
    r = t < r ? t : r;
  }
  double bytes = 2.0 * o * (PROBE / r);
  calib_min = bytes < 64 * 1024 ? 64 * 1024 : bytes > (64u << 20) ? (64u << 20) : (size_t)bytes;
  if (getenv("TURBOBLAKE_TRACE") != NULL) {
    fprintf(stderr, "turboblake: engine %.1f us a job, C %.2f GB/s: subtrees from %zu bytes\n",
            o * 1e6, PROBE / r / 1e9, calib_min);
  }
}

static size_t bend_min(const uint8_t* input, size_t input_len) {
  size_t fixed = bend_fixed();
  if (fixed != 0) {
    return fixed;
  }
  static pthread_once_t once = PTHREAD_ONCE_INIT;
  if (calib_min == SIZE_MAX && input_len >= PROBE) {
    calib_input = input;
    pthread_once(&once, calibrate);
  }
  return calib_min;
}

static void parent_cv(const uint32_t key[8], uint8_t flags, const uint8_t l[32],
                      const uint8_t r[32], uint8_t out[32]) {
  uint8_t block[BLAKE3_BLOCK_LEN];
  uint32_t cv[8];
  memcpy(block, l, 32);
  memcpy(block + 32, r, 32);
  memcpy(cv, key, 32);
  blake3_compress_in_place(cv, block, BLAKE3_BLOCK_LEN, 0, flags | PARENT);
  store_cv_words(out, cv);
}

// BLAKE3's split: the left subtree takes the largest power of two of
// chunks below the total (upstream's left_subtree_len).
static uint64_t left_len(uint64_t len) {
  uint64_t full = (len - 1) / BLAKE3_CHUNK_LEN, p = 1;
  while (p * 2 <= full) {
    p *= 2;
  }
  return p * BLAKE3_CHUNK_LEN;
}

// Merges n span CVs, in place, into cvs[0], as BLAKE3's left-full tree.
static void merge(const uint32_t key[8], uint8_t flags, uint8_t (*cvs)[32], uint32_t n) {
  if (n < 2) {
    return;
  }
  uint32_t p = 1;
  while (p * 2 <= n - 1) {
    p *= 2;
  }
  merge(key, flags, cvs, p);
  merge(key, flags, cvs + p, n - p);
  parent_cv(key, flags, cvs[0], cvs[p], cvs[0]);
}

int turboblake_subtree(const uint8_t* input, size_t input_len, const uint32_t key[8],
                        uint64_t chunk_counter, uint8_t flags, uint8_t out[2 * BLAKE3_OUT_LEN]) {
#ifdef TURBOBLAKE_GPU
  if (tbg_subtree(input, input_len, key, chunk_counter, flags, out)) {
    return 1;
  }
#endif
  if (input_len <= BLAKE3_CHUNK_LEN || input_len < bend_min(input, input_len)) {
    return 0;
  }
  // The engine takes every mode (key and flags), and 64-bit chunk counters
  // if it says so.
  uint64_t chunks = (input_len + BLAKE3_CHUNK_LEN - 1) / BLAKE3_CHUNK_LEN;
  if (chunk_counter + chunks > (1ull << 32) && (b3e_hi == NULL || !b3e_hi())) {
    return 0;
  }
  // The two children: below a span, one span each; past it, the left is
  // whole spans (a power of two of them) and the right the rest. Spans the
  // engine reads in place are up to 1 GiB; copied ones 64 MiB, so their
  // copies overlap the hashing of the ones before.
  uint64_t left = left_len(input_len);
  uint64_t most = b3e_inside(input, input_len - input_len % 64) ? SPAN_MAX : SPAN_COPY;
  uint64_t span = left < most ? left : most;
  uint64_t nl = left / span, n = nl + (input_len - left + span - 1) / span;
  // Each span keeps its counter's high word: a subtree's counter is a
  // multiple of its size, so spans (powers of two of at most 2^20 chunks)
  // start at multiples of theirs and none crosses a multiple of 2^32.
  if (n > 1u << 16 || chunk_counter % (span / BLAKE3_CHUNK_LEN) != 0) {
    return 0;
  }
  const unsigned char** p = malloc(n * sizeof *p);
  uint64_t* len = malloc(n * sizeof *len);
  uint64_t* cb = malloc(n * sizeof *cb);
  uint8_t (*cvs)[32] = malloc(n * 32);
  int ok = p != NULL && len != NULL && cb != NULL && cvs != NULL;
  for (uint64_t i = 0, at = 0; ok && i < n; i += 1, at += span) {
    p[i] = input + at;
    len[i] = input_len - at < span ? input_len - at : span;
    cb[i] = chunk_counter + at / BLAKE3_CHUNK_LEN;
  }
  if (ok) {
    ok = b3e_hash_k((uint32_t)n, p, len, cb, key, flags, cvs);
  }
  if (ok) {
    merge(key, flags, cvs, (uint32_t)nl);
    merge(key, flags, cvs + nl, (uint32_t)(n - nl));
    memcpy(out, cvs[0], 32);
    memcpy(out + 32, cvs[nl], 32);
  }
  free(p);
  free(len);
  free(cb);
  free(cvs);
  return ok;
}

int turboblake_running(void) {
  return b3e_window() != NULL;
}

// The GPU
// -------

#ifdef TURBOBLAKE_GPU
// blake3.c's hasher steps (hasher_merge_cv_stack, hasher_push_cv), for
// bytes the CPU cannot read: blake3_hasher's fields are public, and this
// is the same blake3.c.
static void hasher_merge(blake3_hasher* self, uint64_t total_len) {
  size_t post = (size_t)popcnt(total_len);
  while (self->cv_stack_len > post) {
    uint8_t* parent = &self->cv_stack[(self->cv_stack_len - 2) * BLAKE3_OUT_LEN];
    uint32_t cv[8];
    memcpy(cv, self->key, 32);
    blake3_compress_in_place(cv, parent, BLAKE3_BLOCK_LEN, 0, self->chunk.flags | PARENT);
    store_cv_words(parent, cv);
    self->cv_stack_len -= 1;
  }
}

static void hasher_push(blake3_hasher* self, const uint8_t cv[BLAKE3_OUT_LEN], uint64_t counter) {
  hasher_merge(self, counter);
  memcpy(&self->cv_stack[self->cv_stack_len * BLAKE3_OUT_LEN], cv, BLAKE3_OUT_LEN);
  self->cv_stack_len += 1;
}

// A full chunk state, with more input to come: its CV goes on the stack,
// as blake3_hasher_update does when the next bytes arrive.
static void hasher_flush(blake3_hasher* self) {
  blake3_chunk_state* c = &self->chunk;
  if ((size_t)c->blocks_compressed * BLAKE3_BLOCK_LEN + c->buf_len < BLAKE3_CHUNK_LEN) {
    return;
  }
  uint32_t cv[8];
  uint8_t out[BLAKE3_OUT_LEN];
  memcpy(cv, c->cv, 32);
  blake3_compress_in_place(cv, c->buf, c->buf_len, c->chunk_counter,
                           c->flags | (c->blocks_compressed == 0 ? CHUNK_START : 0) | CHUNK_END);
  store_cv_words(out, cv);
  hasher_push(self, out, c->chunk_counter);
  memcpy(c->cv, self->key, 32);
  c->chunk_counter += 1;
  memset(c->buf, 0, BLAKE3_BLOCK_LEN);
  c->buf_len = 0;
  c->blocks_compressed = 0;
}

// Bytes of GPU memory through the CPU: copied, then a plain update.
static int host_update(blake3_hasher* self, int kind, void* obj, uint64_t off, uint64_t len,
                       void* stream) {
  uint8_t* buf = malloc(len);
  int ok = buf != NULL && tbg_read(kind, obj, off, len, stream, buf);
  if (ok) {
    blake3_hasher_update(self, buf, len);
  }
  free(buf);
  return ok;
}

// blake3_hasher_update's loop over GPU memory: the bytes that finish a
// chunk, and subtrees below tbg_dev_min(), go through the CPU; the rest are
// subtrees the GPU hashes into the two CVs blake3.c would push.
static int dev_update(blake3_hasher* self, int kind, void* obj, uint64_t off, uint64_t len,
                      void* stream) {
  size_t have = (size_t)self->chunk.blocks_compressed * BLAKE3_BLOCK_LEN + self->chunk.buf_len;
  if (have > 0) {
    uint64_t take = BLAKE3_CHUNK_LEN - have < len ? BLAKE3_CHUNK_LEN - have : len;
    if (!host_update(self, kind, obj, off, take, stream)) {
      return 0;
    }
    off += take;
    len -= take;
  }
  uint64_t small = tbg_dev_min();
  while (len > BLAKE3_CHUNK_LEN) {
    hasher_flush(self);
    uint64_t sub = round_down_to_power_of_2(len);
    uint64_t so_far = self->chunk.chunk_counter * BLAKE3_CHUNK_LEN;
    while (((sub - 1) & so_far) != 0) {
      sub /= 2;
    }
    if (sub < small || sub <= BLAKE3_CHUNK_LEN) {
      // whole chunks: the update keeps the last one in the chunk state
      if (!host_update(self, kind, obj, off, sub, stream)) {
        return 0;
      }
    } else {
      uint8_t pair[2 * BLAKE3_OUT_LEN];
      if (!tbg_dev_subtree(kind, obj, off, sub, stream, self->key, self->chunk.chunk_counter,
                           self->chunk.flags, pair)) {
        return 0;
      }
      uint64_t chunks = sub / BLAKE3_CHUNK_LEN;
      hasher_push(self, pair, self->chunk.chunk_counter);
      hasher_push(self, pair + BLAKE3_OUT_LEN, self->chunk.chunk_counter + chunks / 2);
      self->chunk.chunk_counter += chunks;
    }
    off += sub;
    len -= sub;
  }
  if (len > 0) {
    hasher_flush(self);
    return host_update(self, kind, obj, off, len, stream);
  }
  return 1;
}

int turboblake_gpu(void) {
  return tbg_backend();
}

int turboblake_hasher_update_metal(blake3_hasher* self, void* buffer, size_t offset, size_t len) {
  if (len == 0) {
    return 1;
  }
  if (buffer == NULL || tbg_backend() != TURBOBLAKE_GPU_METAL) {
    return 0;
  }
  uint64_t have = 0;
  uint8_t* p = tbg_metal_contents(buffer, &have);
  if (p != NULL) {
    if (offset > have || len > have - offset) {
      return 0;
    }
    // shared: host memory the GPU reads, through the hook
    int reg = tbg_register_metal(buffer);
    blake3_hasher_update(self, p + offset, len);
    if (reg) {
      tbg_unregister(p);
    }
    return 1;
  }
  blake3_hasher saved = *self;
  if (!dev_update(self, TBG_METAL, buffer, offset, len, NULL)) {
    *self = saved;
    return 0;
  }
  return 1;
}

int turboblake_hasher_update_cuda(blake3_hasher* self, uint64_t device_ptr, size_t len,
                                  void* stream) {
  if (len == 0) {
    return 1;
  }
  if (device_ptr == 0 || tbg_backend() != TURBOBLAKE_GPU_CUDA) {
    return 0;
  }
  blake3_hasher saved = *self;
  if (!dev_update(self, TBG_CUDA, (void*)(uintptr_t)device_ptr, 0, len, stream)) {
    *self = saved;
    return 0;
  }
  return 1;
}

void* turboblake_alloc(size_t len) {
  return tbg_alloc(len);
}

void turboblake_free(void* p) {
  tbg_free(p);
}

int turboblake_register(void* p, size_t len) {
  return tbg_register(p, len);
}

void turboblake_unregister(void* p) {
  tbg_unregister(p);
}
#else
// A build without the GPU backend: the CPU hashes everything.
int turboblake_gpu(void) {
  return 0;
}

int turboblake_hasher_update_metal(blake3_hasher* self, void* buffer, size_t offset, size_t len) {
  (void)self, (void)buffer, (void)offset;
  return len == 0;
}

int turboblake_hasher_update_cuda(blake3_hasher* self, uint64_t device_ptr, size_t len,
                                  void* stream) {
  (void)self, (void)device_ptr, (void)stream;
  return len == 0;
}

void* turboblake_alloc(size_t len) {
  (void)len;
  return NULL;
}

void turboblake_free(void* p) {
  (void)p;
}

int turboblake_register(void* p, size_t len) {
  (void)p, (void)len;
  return 0;
}

void turboblake_unregister(void* p) {
  (void)p;
}
#endif
