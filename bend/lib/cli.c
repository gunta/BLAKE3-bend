// The test CLI for libblake3-bend, after the official c/main.c (whose CPU
// feature loop is x86-only): hashes stdin through blake3.h and prints hex.
//   cli [--length N] [--seek N] [--keyed HEX] [--derive-key CONTEXT] [--split N]
// --split N feeds the hasher N bytes per update, to cross every subtree
// edge the hook sees; the output must not change.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "blake3.h"

static int hexval(char c) {
  return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

int main(int argc, char** argv) {
  size_t out_len = BLAKE3_OUT_LEN, split = 0;
  uint64_t seek = 0;
  uint8_t key[BLAKE3_KEY_LEN];
  const char* context = NULL;
  int keyed = 0;
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
    } else if (!strcmp(argv[i], "--derive-key") && i + 1 < argc) {
      context = argv[++i];
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
  blake3_hasher h;
  if (keyed) {
    blake3_hasher_init_keyed(&h, key);
  } else if (context != NULL) {
    blake3_hasher_init_derive_key(&h, context);
  } else {
    blake3_hasher_init(&h);
  }
  for (size_t at = 0; at < len;) {
    size_t n = split == 0 || len - at < split ? len - at : split;
    blake3_hasher_update(&h, buf + at, n);
    at += n;
  }
  uint8_t* out = malloc(out_len ? out_len : 1);
  blake3_hasher_finalize_seek(&h, seek, out, out_len);
  for (size_t i = 0; i < out_len; i += 1) {
    printf("%02x", out[i]);
  }
  printf("\n");
  return 0;
}
