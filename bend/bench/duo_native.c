// CPU + GPU on one input in one process: libturboblake's split (ADR 0017),
// the Bend engine on the CPU side and the native kernel on the GPU side.
// Fills the 2^d words of bench/mem.bend (so the digest is mem's and duo's)
// and hashes them reps + 1 times through blake3.h, the first a warm-up.
//   duo_native <d> <reps> <mode>
// mode:
//   cpu    malloc'd memory: the engine alone, as every caller gets today
//   split  turboblake_alloc'd memory (a shared Metal buffer, CUDA pinned
//          memory): the hook splits it between the engine and the GPU, at
//          TURBOBLAKE_GPU_SHARE, else at the share the measured rates balance
//   gpu    GPU memory (a private Metal buffer, CUDA device memory):
//          turboblake_hasher_update_metal/_cuda, the GPU alone
// Prints "us <micros> <digest>" a round. bench/duo.py --native runs it.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "blake3.h"
#include "turboblake.h"

void* tbg_upload(const void* p, uint64_t len, uint64_t pad, int gpu_only);

static double now_us(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e6 + t.tv_nsec * 1e-3;
}

int main(int argc, char** argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: duo_native <d> <reps> cpu|split|gpu\n");
    return 2;
  }
  int d = atoi(argv[1]), reps = atoi(argv[2]);
  const char* mode = argv[3];
  size_t words = (size_t)1 << d, len = words * 4;
  int split = !strcmp(mode, "split"), gpu = !strcmp(mode, "gpu");
  if (!split && !gpu && strcmp(mode, "cpu") != 0) {
    fprintf(stderr, "mode is cpu, split or gpu\n");
    return 2;
  }
  uint32_t* p = split ? turboblake_alloc(len) : malloc(len);
  if (p == NULL) {
    fprintf(stderr, "no memory for %s\n", mode);
    return 1;
  }
  for (size_t j = 0; j < words; j += 1) {
    p[j] = (uint32_t)j * 2654435761u + 12345u;
  }
  void* dev = NULL;
  if (gpu) {
    dev = turboblake_gpu() ? tbg_upload(p, len, 0, 1) : NULL;
    if (dev == NULL) {
      fprintf(stderr, "no GPU backend\n");
      return 1;
    }
  }
  for (int r = 0; r <= reps; r += 1) {
    uint8_t out[32];
    blake3_hasher h;
    double t0 = now_us();
    blake3_hasher_init(&h);
    int ok = 1;
    if (gpu) {
      ok = turboblake_gpu() == TURBOBLAKE_GPU_METAL
          ? turboblake_hasher_update_metal(&h, dev, 0, len)
          : turboblake_hasher_update_cuda(&h, (uint64_t)(uintptr_t)dev, len, NULL);
    } else {
      blake3_hasher_update(&h, p, len);
    }
    blake3_hasher_finalize(&h, out, 32);
    double t = now_us() - t0;
    if (!ok) {
      fprintf(stderr, "the GPU update failed\n");
      return 1;
    }
    printf("us %.0f ", t);
    for (int i = 0; i < 32; i += 1) {
      printf("%02x", out[i]);
    }
    printf("\n");
    fflush(stdout);
  }
  return 0;
}
