// In-memory throughput of a blake3.h library: one update of the whole
// buffer and a finalize, `reps` times, after one warm-up run.
//   bench <bytes> <reps>    prints "us <median> min <min> bytes <n> <hex>"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "blake3.h"

static double now_us(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e6 + t.tv_nsec * 1e-3;
}

static int cmp(const void* a, const void* b) {
  double x = *(const double*)a, y = *(const double*)b;
  return x < y ? -1 : x > y;
}

int main(int argc, char** argv) {
  size_t n = argc > 1 ? (size_t)strtoull(argv[1], NULL, 10) : 1 << 20;
  int reps = argc > 2 ? atoi(argv[2]) : 10;
  unsigned char* buf = malloc(n ? n : 1);
  for (size_t i = 0; i < n; i += 1) {
    buf[i] = (unsigned char)(i * 2654435761u >> 13);
  }
  double* t = malloc(sizeof(double) * (reps + 1));
  uint8_t out[32];
  for (int r = 0; r <= reps; r += 1) {
    double t0 = now_us();
    blake3_hasher h;
    blake3_hasher_init(&h);
    blake3_hasher_update(&h, buf, n);
    blake3_hasher_finalize(&h, out, 32);
    t[r] = now_us() - t0;
  }
  qsort(t + 1, reps, sizeof(double), cmp);
  printf("us %.1f min %.1f bytes %zu ", t[1 + reps / 2], t[1], n);
  for (int i = 0; i < 32; i += 1) {
    printf("%02x", out[i]);
  }
  printf("\n");
  return 0;
}
