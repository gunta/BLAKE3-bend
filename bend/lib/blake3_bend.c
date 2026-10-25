// libblake3-bend's one hook into the official C library
// ======================================================
//
// blake3.c (patched by build.sh) asks blake3_bend_subtree first whenever an
// update reaches a complete power-of-two subtree of 2+ chunks: the work its
// SIMD loop would do on one thread. If the subtree is big enough to beat
// the trip to the engine, it is cut into spans of at most 1 GiB (whole
// subtrees), the Bend engine (engine.bend) hashes every span at once on
// every core, and the span CVs merge here, as parent nodes, into the two
// CVs the C library expects. Anything else (small subtrees, a forked child,
// an engine that failed to start) answers 0 and C hashes it as upstream does.
//
// Environment:
//   BLAKE3_BEND=0          never use the engine
//   BLAKE3_BEND_MIN=n      smallest subtree in bytes for the engine (default:
//                          calibrated at the first big update)
//   BLAKE3_BEND_THREADS=n  the engine's threads (default: every core)

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "blake3_impl.h"
#include "blake3_bend.h"

int b3e_hash(uint32_t n, const unsigned char* const* p, const uint64_t* len,
             const uint64_t* cb, unsigned char (*out)[32]);
const void* b3e_window(void);

#define SPANS 64
#define SPAN_MAX (1ull << 30)
#define STAGED 2

// The smallest subtree the engine takes: BLAKE3_BEND_MIN if set, else
// calibrated on the first subtree that might qualify. The engine costs a
// fixed O per job (waking its threads; ~0.1 ms on a Mac, more in a
// sandbox) and then runs ~10x the one-thread SIMD rate R, so it wins past
// about O * R bytes; it takes subtrees from twice that.
static size_t bend_fixed(void) {
  static size_t min = 1;
  if (min == 1) {
    const char* off = getenv("BLAKE3_BEND");
    const char* m = getenv("BLAKE3_BEND_MIN");
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
  if (getenv("BLAKE3_BEND_TRACE") != NULL) {
    fprintf(stderr, "blake3-bend: engine %.1f us a job, C %.2f GB/s: subtrees from %zu bytes\n",
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

// The CVs of the n spans of `span` bytes each, from input and chunk
// counter cb, in jobs the engine takes: every span at once when the input
// sits in the engine's window, STAGED at a time when it must be copied.
static int span_cvs(const uint8_t* input, uint64_t span, uint32_t n, uint64_t cb,
                    uint8_t (*cvs)[32]) {
  const uint8_t* lo = (const uint8_t*)b3e_window();
  int inside = lo != NULL && input >= lo && (uintptr_t)input % 8 == 0
            && (uint64_t)(input - lo) / 8 + (uint64_t)n * span / 8 < (1ull << 40);
  uint32_t per = inside ? SPANS : STAGED;
  for (uint32_t i = 0; i < n; i += per) {
    uint32_t k = n - i < per ? n - i : per;
    const unsigned char* p[SPANS];
    uint64_t len[SPANS], c[SPANS];
    for (uint32_t j = 0; j < k; j += 1) {
      p[j] = input + (uint64_t)(i + j) * span;
      len[j] = span;
      c[j] = cb + (uint64_t)(i + j) * (span / BLAKE3_CHUNK_LEN);
    }
    if (!b3e_hash(k, p, len, c, cvs + i)) {
      return 0;
    }
  }
  return 1;
}

// Merges n (a power of two) CVs, in place, into cvs[0].
static void merge(const uint32_t key[8], uint8_t flags, uint8_t (*cvs)[32], uint32_t n) {
  for (; n > 1; n /= 2) {
    for (uint32_t i = 0; i < n / 2; i += 1) {
      parent_cv(key, flags, cvs[2 * i], cvs[2 * i + 1], cvs[i]);
    }
  }
}

int blake3_bend_subtree(const uint8_t* input, size_t input_len, const uint32_t key[8],
                        uint64_t chunk_counter, uint8_t flags, uint8_t out[2 * BLAKE3_OUT_LEN]) {
  if (input_len < 2 * BLAKE3_CHUNK_LEN || input_len < bend_min(input, input_len)) {
    return 0;
  }
  // The engine hashes BLAKE3's default mode, 32-bit chunk counters.
  if (flags != 0 || memcmp(key, IV, sizeof IV) != 0
      || chunk_counter + input_len / BLAKE3_CHUNK_LEN > (1ull << 32)) {
    return 0;
  }
  uint64_t half = input_len / 2;
  uint64_t span = half < SPAN_MAX ? half : SPAN_MAX;
  uint32_t n = (uint32_t)(half / span);  // spans a half (a power of two)
  if (2ull * n > 4096) {
    return 0;
  }
  uint8_t (*cvs)[32] = malloc(2ull * n * 32);
  if (cvs == NULL) {
    return 0;
  }
  int ok = span_cvs(input, span, 2 * n, chunk_counter, cvs);
  if (ok) {
    merge(key, flags, cvs, n);
    merge(key, flags, cvs + n, n);
    memcpy(out, cvs[0], 32);
    memcpy(out + 32, cvs[n], 32);
  }
  free(cvs);
  return ok;
}

int blake3_bend_running(void) {
  return b3e_window() != NULL;
}
