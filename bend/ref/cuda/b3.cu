// Native CUDA BLAKE3: the kernels of ../metal/b3.metal for NVIDIA GPUs, and
// libturboblake's CUDA kernels (ADR 0013), which it ships as PTX
// (bend/lib/gen_gpu.sh). b3cuda.cu is the reference host.
//
// leafK:  thread t hashes chunks [tK, tK + K) one after another, folds them
//         with a CV stack, then groups of 2^fold lanes of a warp fold their
//         subtrees with shuffles: one CV per 2^fold K chunks (fold = 5: a
//         whole warp). K is 1, 4, 16 or 64 (leaf1 .. leaf64).
// merge:  one CV per thread, the same fold: one CV per 2^fold nodes.
// The reference host runs leaf once and merge until one node is left, the
// last merge as ROOT; the library stops at CVs of whole subtrees and merges
// those on the CPU, so it can finish any mode and output length there.
#include "../b3core.h"

struct Span {
  b3u32 nch;     // chunks in the input
  b3u32 last;    // bytes in the last chunk: 1..1024, 0 for the empty input
  b3u32 n;       // merge: nodes in this level
  b3u32 whole;   // this dispatch folds the input to one node (its last merge is ROOT)
  b3u32 fold;    // log2 of the lanes folded into each output CV, 0..5
  b3u32 flags;   // the mode's flags: 0, KEYED_HASH or DERIVE_KEY_*
  b3u32 ctr_lo;  // the first chunk's counter, low and high words
  b3u32 ctr_hi;
  b3u32 key[8];  // the IV, the key, or the derived context key
};

// The input's last block when it is short (blen < 64): only its blen bytes
// are read, so the input needs no padding past its end.
B3_FN b3u32 tail_word(const unsigned char *p, b3u32 w, b3u32 blen) {
  b3u32 x = 0;
  for (b3u32 b = 0; b < 4; b++)
    if (4 * w + b < blen) x |= (b3u32)p[4 * w + b] << (8 * b);
  return x;
}

// The CV of chunk c, whose counter is ctr: n blocks, the last of blen bytes;
// fl is the mode's flags, root ROOT if this chunk is the whole input. The
// input is read-only for the whole kernel, so it goes through __ldg.
B3_FN void chunk_cv(b3u32 *cv, const b3u32 *key, const uint4 *__restrict__ in, b3u32 c,
                    unsigned long long ctr, b3u32 n, b3u32 blen, b3u32 fl, b3u32 root) {
  for (int i = 0; i < 8; i++) cv[i] = key[i];
  const uint4 *p = in + (unsigned long long)c * 64;
  for (b3u32 b = 0; b < n; b++) {
    b3u32 m[16];
    bool end = b + 1 == n;
    if (end && blen < 64) {
      const unsigned char *q = (const unsigned char *)p;
#pragma unroll
      for (b3u32 w = 0; w < 16; w++) m[w] = tail_word(q, w, blen);
    } else {
      uint4 q0 = __ldg(p), q1 = __ldg(p + 1), q2 = __ldg(p + 2), q3 = __ldg(p + 3);
      m[0] = q0.x;  m[1] = q0.y;  m[2] = q0.z;  m[3] = q0.w;
      m[4] = q1.x;  m[5] = q1.y;  m[6] = q1.z;  m[7] = q1.w;
      m[8] = q2.x;  m[9] = q2.y;  m[10] = q2.z; m[11] = q2.w;
      m[12] = q3.x; m[13] = q3.y; m[14] = q3.z; m[15] = q3.w;
    }
    p += 4;
    b3u32 f = fl | (b == 0 ? B3_CHUNK_START : 0u) | (end ? B3_CHUNK_END | root : 0u);
    b3_compress(cv, m, (b3u32)ctr, (b3u32)(ctr >> 32), end ? blen : 64u, f);
  }
}

B3_FN void cv_copy(b3u32 *d, const b3u32 *s) {
  for (int i = 0; i < 8; i++) d[i] = s[i];
}

// Pushes chunk i's CV (of cnt in this thread) on the stack of complete
// subtrees, as in the reference implementation: merge while i + 1 has
// trailing zeros, except after the last chunk (the fold does those).
B3_FN void push(b3u32 (*st)[8], b3u32 &sd, b3u32 *cv, const b3u32 *key, b3u32 i,
                b3u32 cnt, b3u32 fl) {
  for (b3u32 t = i + 1; (t & 1) == 0 && i + 1 < cnt; t >>= 1) {
    b3u32 r[8];
    cv_copy(r, cv);
    sd--;
    b3_parent(cv, key, st[sd], r, fl);
  }
  cv_copy(st[sd], cv);
  sd++;
}

// Folds the CVs of the c lanes of a group (g is this lane's index in it)
// into the group's lane 0, pairing level by level, over groups of 2^fold
// lanes; the merge that leaves one node takes ROOT when the dispatch is
// whole. Every lane of the warp must call it: the shuffles name all 32.
B3_FN void warp_fold(b3u32 *cv, const b3u32 *key, b3u32 g, b3u32 c, b3u32 fold,
                     bool whole, b3u32 fl) {
  for (b3u32 s = 1; s < (1u << fold); s <<= 1) {
    b3u32 r[8];
    for (int i = 0; i < 8; i++) r[i] = __shfl_down_sync(0xffffffffu, cv[i], s);
    if ((g & (2 * s - 1)) == 0 && g + s < c) {
      b3u32 l[8];
      cv_copy(l, cv);
      b3_parent(cv, key, l, r, fl | (whole && g == 0 && c <= 2 * s ? B3_ROOT : 0u));
    }
  }
}

template <b3u32 K>
B3_FN void leaf_k(const uint4 *__restrict__ in, b3u32 *out, const Span &sp) {
  b3u32 tid = blockIdx.x * blockDim.x + threadIdx.x;
  b3u32 lane = threadIdx.x & 31;
  b3u32 nth = (sp.nch + K - 1) / K;
  b3u32 key[8];
  for (int i = 0; i < 8; i++) key[i] = sp.key[i];
  b3u32 fl = sp.flags;
  unsigned long long ctr0 = (unsigned long long)sp.ctr_hi << 32 | sp.ctr_lo;
  b3u32 cv[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  if (tid < nth) {
    b3u32 c0 = tid * K;
    b3u32 cnt = min(K, sp.nch - c0);
    bool solo = sp.whole && nth == 1;
    b3u32 st[8][8];
    b3u32 sd = 0;
    for (b3u32 i = 0; i < cnt; i++) {
      b3u32 c = c0 + i;
      bool lastc = c + 1 == sp.nch;
      b3u32 nb = lastc ? max(1u, (sp.last + 63) / 64) : 16u;
      b3u32 bl = lastc ? sp.last - 64 * (nb - 1) : 64u;
      chunk_cv(cv, key, in, c, ctr0 + c, nb, bl, fl, solo && sp.nch == 1 ? B3_ROOT : 0u);
      push(st, sd, cv, key, i, cnt, fl);
    }
    // A partial run (the input's tail) folds what is left right to left.
    sd--;
    cv_copy(cv, st[sd]);
    while (sd > 0) {
      b3u32 r[8];
      cv_copy(r, cv);
      sd--;
      b3_parent(cv, key, st[sd], r, fl | (solo && sd == 0 ? B3_ROOT : 0u));
    }
  }
  b3u32 g = lane & ((1u << sp.fold) - 1);
  b3u32 base = tid - g;
  b3u32 c = base < nth ? min(1u << sp.fold, nth - base) : 0u;
  warp_fold(cv, key, g, c, sp.fold, sp.whole != 0, fl);
  if (g == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(unsigned long long)(tid >> sp.fold) * 8 + i] = cv[i];
}

extern "C" __global__ void leaf1(const uint4 *__restrict__ in, b3u32 *out, Span sp) {
  leaf_k<1>(in, out, sp);
}
extern "C" __global__ void leaf4(const uint4 *__restrict__ in, b3u32 *out, Span sp) {
  leaf_k<4>(in, out, sp);
}
// The library runs K = 1 and 4 only, so its PTX (B3_LIB) leaves these out.
#ifndef B3_LIB
extern "C" __global__ void leaf16(const uint4 *__restrict__ in, b3u32 *out, Span sp) {
  leaf_k<16>(in, out, sp);
}
extern "C" __global__ void leaf64(const uint4 *__restrict__ in, b3u32 *out, Span sp) {
  leaf_k<64>(in, out, sp);
}
#endif

extern "C" __global__ void merge(const b3u32 *__restrict__ in, b3u32 *out, Span sp) {
  b3u32 tid = blockIdx.x * blockDim.x + threadIdx.x;
  b3u32 lane = threadIdx.x & 31;
  b3u32 key[8];
  for (int i = 0; i < 8; i++) key[i] = sp.key[i];
  b3u32 cv[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  if (tid < sp.n)
    for (int i = 0; i < 8; i++) cv[i] = in[(unsigned long long)tid * 8 + i];
  b3u32 g = lane & ((1u << sp.fold) - 1);
  b3u32 base = tid - g;
  b3u32 c = base < sp.n ? min(1u << sp.fold, sp.n - base) : 0u;
  warp_fold(cv, key, g, c, sp.fold, sp.whole != 0, sp.flags);
  if (g == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(unsigned long long)(tid >> sp.fold) * 8 + i] = cv[i];
}
