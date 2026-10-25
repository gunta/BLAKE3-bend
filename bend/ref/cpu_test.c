// The GPU references' algorithm on the CPU: b3core.h's compression, and the
// leaf/merge kernels' tree logic with a 32-lane SIMD group emulated lane by
// lane. Prints "len hash" for every official vector length and leaf size K,
// for ../test/check.py, so the CUDA kernels (which this machine may not
// run) are checked against the same logic as the Metal ones.
//   cc -O2 -o build/cpu_test cpu_test.c && build/cpu_test | python3 ../test/check.py
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "b3core.h"

typedef struct { b3u32 nch, last, n, whole; } Span;

static void chunk_cv(b3u32 *cv, const b3u32 *in, b3u32 c, b3u32 n, b3u32 blen,
                     b3u32 root) {
  b3_iv(cv);
  for (b3u32 b = 0; b < n; b++) {
    int end = b + 1 == n;
    b3u32 fl = (b == 0 ? B3_CHUNK_START : 0u) | (end ? B3_CHUNK_END | root : 0u);
    b3_compress(cv, in + c * 256 + b * 16, c, end ? blen : 64u, fl);
  }
}

static void push(b3u32 (*st)[8], b3u32 *sd, b3u32 *cv, b3u32 i, b3u32 cnt) {
  for (b3u32 t = i + 1; (t & 1) == 0 && i + 1 < cnt; t >>= 1) {
    b3u32 r[8];
    memcpy(r, cv, 32);
    --*sd;
    b3_parent(cv, st[*sd], r, 0u);
  }
  memcpy(st[*sd], cv, 32);
  ++*sd;
}

// The SIMD fold, one level at a time over all 32 lanes: every lane reads its
// shuffle partner before any lane merges, as the hardware does.
static void simd_fold(b3u32 cv[32][8], b3u32 c, int whole) {
  for (b3u32 s = 1; s < 32; s <<= 1) {
    b3u32 r[32][8];
    for (b3u32 lane = 0; lane < 32; lane++)
      memcpy(r[lane], lane + s < 32 ? cv[lane + s] : cv[lane], 32);
    for (b3u32 lane = 0; lane < 32; lane++)
      if ((lane & (2 * s - 1)) == 0 && lane + s < c) {
        b3u32 l[8];
        memcpy(l, cv[lane], 32);
        b3_parent(cv[lane], l, r[lane], whole && lane == 0 && c <= 2 * s ? B3_ROOT : 0u);
      }
  }
}

// One leaf dispatch: nth threads in groups of 32; out gets a CV per group.
static b3u32 leaf(const b3u32 *in, b3u32 *out, Span sp, b3u32 k) {
  b3u32 nth = (sp.nch + k - 1) / k;
  for (b3u32 base = 0; base < nth; base += 32) {
    b3u32 cv[32][8] = {{0}};
    for (b3u32 lane = 0; lane < 32 && base + lane < nth; lane++) {
      b3u32 tid = base + lane, c0 = tid * k;
      b3u32 cnt = k < sp.nch - c0 ? k : sp.nch - c0;
      int solo = sp.whole && nth == 1;
      b3u32 st[8][8], sd = 0;
      for (b3u32 i = 0; i < cnt; i++) {
        b3u32 c = c0 + i;
        int lastc = c + 1 == sp.nch;
        b3u32 nb = lastc ? (sp.last + 63) / 64 : 16u;
        if (nb == 0) nb = 1;
        b3u32 bl = lastc ? sp.last - 64 * (nb - 1) : 64u;
        chunk_cv(cv[lane], in, c, nb, bl, solo && sp.nch == 1 ? B3_ROOT : 0u);
        push(st, &sd, cv[lane], i, cnt);
      }
      sd--;
      memcpy(cv[lane], st[sd], 32);
      while (sd > 0) {
        b3u32 r[8];
        memcpy(r, cv[lane], 32);
        sd--;
        b3_parent(cv[lane], st[sd], r, solo && sd == 0 ? B3_ROOT : 0u);
      }
    }
    b3u32 c = nth - base < 32 ? nth - base : 32;
    simd_fold(cv, c, sp.whole != 0);
    memcpy(out + base / 32 * 8, cv[0], 32);
  }
  return (nth + 31) / 32;
}

static b3u32 merge(const b3u32 *in, b3u32 *out, Span sp) {
  for (b3u32 base = 0; base < sp.n; base += 32) {
    b3u32 cv[32][8] = {{0}};
    for (b3u32 lane = 0; lane < 32 && base + lane < sp.n; lane++)
      memcpy(cv[lane], in + (base + lane) * 8, 32);
    b3u32 c = sp.n - base < 32 ? sp.n - base : 32;
    simd_fold(cv, c, sp.whole != 0);
    memcpy(out + base / 32 * 8, cv[0], 32);
  }
  return (sp.n + 31) / 32;
}

static void hash(const b3u32 *in, b3u32 len, b3u32 k, b3u32 out[8]) {
  b3u32 nch = len == 0 ? 1 : (len + 1023) / 1024;
  b3u32 last = len - (nch - 1) * 1024;
  b3u32 nth = (nch + k - 1) / k;
  b3u32 *a = calloc(nth + 32, 32), *b = calloc(nth + 32, 32);
  Span s = {nch, last, 0, nth <= 32};
  b3u32 n = leaf(in, a, s, k);
  while (n > 1) {
    Span m = {nch, last, n, n <= 32};
    n = merge(a, b, m);
    b3u32 *t = a; a = b; b = t;
  }
  memcpy(out, a, 32);
  free(a);
  free(b);
}

int main(void) {
  static const b3u32 lens[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 63, 64, 65, 127, 128, 129,
    1023, 1024, 1025, 2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168,
    7169, 8192, 8193, 16384, 31744, 102400};
  static const b3u32 ks[] = {1, 4, 16, 64};
  for (size_t j = 0; j < sizeof ks / sizeof *ks; j++)
    for (size_t i = 0; i < sizeof lens / sizeof *lens; i++) {
      b3u32 n = lens[i];
      // Little-endian words, zero to the end of the last chunk.
      b3u32 *w = calloc((n + 1023) / 1024 * 256 + 256, 4);
      for (b3u32 x = 0; x < n; x++) w[x / 4] |= (b3u32)(x % 251) << (8 * (x % 4));
      b3u32 cv[8];
      hash(w, n, ks[j], cv);
      printf("%u ", n);
      for (int x = 0; x < 32; x++) printf("%02x", (cv[x / 4] >> (8 * (x % 4))) & 0xff);
      printf("\n");
      free(w);
    }
  return 0;
}
