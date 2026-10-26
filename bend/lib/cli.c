// The test CLI for libturboblake, after the official c/main.c (whose CPU
// feature loop is x86-only): hashes stdin through blake3.h and prints hex.
//   cli [--length N] [--seek N] [--keyed HEX] [--derive-key CONTEXT] [--split N]
//   cli --whole
//   cli --files PATH...
//   cli --gpu [shared|private] [--offset N] [--mix] ...   (and the options above)
//   cli --gpu-info
// --split N feeds the hasher N bytes per update, to cross every subtree
// edge the hook sees; the output must not change. --whole hands the whole
// input (2+ chunks, any length) to the hook at once, as the Rust crate's
// hash() does, and prints the root of its two CVs. --files hashes the
// paths as one engine file job (turboblake's fast path) and prints them as
// b3sum does. --gpu copies the input to GPU memory (on Metal a private
// buffer by default, or a shared one), N bytes in (--offset), and feeds it
// with turboblake_hasher_update_metal/_cuda; --mix alternates GPU and host
// updates. --gpu-info prints the backend (none, metal, cuda).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "blake3.h"
#include "turboblake.h"

int b3e_files(uint32_t n, const char* const* paths, unsigned char (*out)[32], int* err);
#ifdef TURBOBLAKE_GPU
void* tbg_upload(const void* p, uint64_t len, uint64_t pad, int gpu_only);
void tbg_drop(void* obj);
#else
static void* tbg_upload(const void* p, uint64_t len, uint64_t pad, int gpu_only) {
  (void)p, (void)len, (void)pad, (void)gpu_only;
  return NULL;
}
static void tbg_drop(void* obj) {
  (void)obj;
}
#endif

void blake3_compress_in_place(uint32_t cv[8], const uint8_t block[64], uint8_t block_len,
                              uint64_t counter, uint8_t flags);

static int hexval(char c) {
  return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

static int files(int n, char** paths) {
  unsigned char (*out)[32] = malloc((size_t)(n ? n : 1) * 32);
  int* err = malloc((size_t)(n ? n : 1) * sizeof(int));
  if (!b3e_files((uint32_t)n, (const char* const*)paths, out, err)) {
    fprintf(stderr, "no engine\n");
    return 1;
  }
  int bad = 0;
  for (int i = 0; i < n; i += 1) {
    if (err[i] != 0) {
      fprintf(stderr, "b3sum: %s: %s (os error %d)\n", paths[i], strerror(err[i]), err[i]);
      bad = 1;
      continue;
    }
    for (int b = 0; b < 32; b += 1) {
      printf("%02x", out[i][b]);
    }
    printf("  %s\n", paths[i]);
  }
  return bad;
}

int main(int argc, char** argv) {
  if (argc > 1 && !strcmp(argv[1], "--files")) {
    return files(argc - 2, argv + 2);
  }
  if (argc > 1 && !strcmp(argv[1], "--gpu-info")) {
    int g = turboblake_gpu();
    printf("%s\n", g == TURBOBLAKE_GPU_METAL ? "metal" : g == TURBOBLAKE_GPU_CUDA ? "cuda" : "none");
    return 0;
  }
  size_t out_len = BLAKE3_OUT_LEN, split = 0, offset = 0;
  uint64_t seek = 0;
  uint8_t key[BLAKE3_KEY_LEN];
  const char* context = NULL;
  int keyed = 0, whole = 0, gpu = 0, gpu_only = 1, mix = 0;
  for (int i = 1; i < argc; i += 1) {
    if (!strcmp(argv[i], "--length") && i + 1 < argc) {
      out_len = (size_t)strtoull(argv[++i], NULL, 10);
    } else if (!strcmp(argv[i], "--seek") && i + 1 < argc) {
      seek = strtoull(argv[++i], NULL, 10);
    } else if (!strcmp(argv[i], "--split") && i + 1 < argc) {
      split = (size_t)strtoull(argv[++i], NULL, 10);
    } else if (!strcmp(argv[i], "--keyed") && i + 1 < argc) {
      const char* h = argv[++i];
      if (strlen(h) != 2 * BLAKE3_KEY_LEN) {
        fprintf(stderr, "--keyed takes 64 hex digits\n");
        return 2;
      }
      for (int k = 0; k < BLAKE3_KEY_LEN; k += 1) {
        key[k] = (uint8_t)(hexval(h[2 * k]) << 4 | hexval(h[2 * k + 1]));
      }
      keyed = 1;
    } else if (!strcmp(argv[i], "--whole")) {
      whole = 1;
    } else if (!strcmp(argv[i], "--derive-key") && i + 1 < argc) {
      context = argv[++i];
    } else if (!strcmp(argv[i], "--gpu")) {
      gpu = 1;
      if (i + 1 < argc && (!strcmp(argv[i + 1], "shared") || !strcmp(argv[i + 1], "private"))) {
        gpu_only = !strcmp(argv[++i], "private");
      }
    } else if (!strcmp(argv[i], "--offset") && i + 1 < argc) {
      offset = (size_t)strtoull(argv[++i], NULL, 10);
    } else if (!strcmp(argv[i], "--mix")) {
      mix = 1;
    } else {
      fprintf(stderr, "usage: cli [--length N] [--seek N] [--keyed HEX] [--derive-key CTX] [--split N]\n");
      return 2;
    }
  }
  size_t cap = 1 << 20, len = 0;
  uint8_t* buf = malloc(cap);
  for (;;) {
    if (len == cap) {
      buf = realloc(buf, cap *= 2);
    }
    size_t n = fread(buf + len, 1, cap - len, stdin);
    if (n == 0) {
      break;
    }
    len += n;
  }
  if (whole) {
    static const uint32_t iv[8] = { 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
                                    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19 };
    uint8_t pair[64];
    if (len <= 1024 || !turboblake_subtree(buf, len, iv, 0, 0, pair)) {
      fprintf(stderr, "the hook declined\n");
      return 1;
    }
    uint32_t cv[8];
    memcpy(cv, iv, sizeof cv);
    blake3_compress_in_place(cv, pair, 64, 0, 4 | 8);  // PARENT | ROOT
    for (int w = 0; w < 8; w += 1) {
      printf("%02x%02x%02x%02x", cv[w] & 255, cv[w] >> 8 & 255, cv[w] >> 16 & 255, cv[w] >> 24);
    }
    printf("\n");
    return 0;
  }
  blake3_hasher h;
  if (keyed) {
    blake3_hasher_init_keyed(&h, key);
  } else if (context != NULL) {
    blake3_hasher_init_derive_key(&h, context);
  } else {
    blake3_hasher_init(&h);
  }
  void* dev = NULL;
  if (gpu) {
    int g = turboblake_gpu();
    dev = g ? tbg_upload(buf, len, offset, gpu_only) : NULL;
    if (dev == NULL) {
      fprintf(stderr, "no GPU backend\n");
      return 3;
    }
  }
  for (size_t at = 0, k = 0; at < len; k += 1) {
    size_t n = split == 0 || len - at < split ? len - at : split;
    if (gpu && !(mix && k % 2 == 1)) {
      int ok = turboblake_gpu() == TURBOBLAKE_GPU_METAL
          ? turboblake_hasher_update_metal(&h, dev, offset + at, n)
          : turboblake_hasher_update_cuda(&h, (uint64_t)(uintptr_t)dev + offset + at, n, NULL);
      if (!ok) {
        fprintf(stderr, "the GPU update failed\n");
        return 1;
      }
    } else {
      blake3_hasher_update(&h, buf + at, n);
    }
    at += n;
  }
  if (dev != NULL) {
    tbg_drop(dev);
  }
  uint8_t* out = malloc(out_len ? out_len : 1);
  blake3_hasher_finalize_seek(&h, seek, out, out_len);
  for (size_t i = 0; i < out_len; i += 1) {
    printf("%02x", out[i]);
  }
  printf("\n");
  return 0;
}
