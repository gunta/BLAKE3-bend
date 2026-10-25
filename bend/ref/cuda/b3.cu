// Native CUDA BLAKE3: the kernels of ../metal/b3.metal for NVIDIA GPUs, the
// reference for a Bend program's CUDA target. b3cuda.cu is the host.
//
// leaf<K>: thread t hashes chunks [tK, tK + K) one after another, folds them
//          with a CV stack, then the 32 lanes of a warp fold their subtrees
//          with shuffles: one CV per 32K chunks.
// merge:   one CV per thread, the same warp fold: one CV per 32 nodes.
// The host runs leaf once and merge until one node is left.
#include "../b3core.h"

struct Span {
  b3u32 nch;   // chunks in the input
  b3u32 last;  // bytes in the last chunk: 1..1024, 0 for the empty input
  b3u32 n;     // merge: nodes in this level
  b3u32 whole; // this dispatch folds the input to one node (its last merge is ROOT)
};

// The CV of chunk c (counter c): n blocks, the last of blen bytes. The
// input is read-only for the whole kernel, so it goes through __ldg.
B3_FN void chunk_cv(b3u32 *cv, const uint4 *__restrict__ in, b3u32 c, b3u32 n,
                    b3u32 blen, b3u32 root) {
  b3_iv(cv);
  const uint4 *p = in + (unsigned long long)c * 64;
  for (b3u32 b = 0; b < n; b++) {
    uint4 q0 = __ldg(p), q1 = __ldg(p + 1), q2 = __ldg(p + 2), q3 = __ldg(p + 3);
    p += 4;
    b3u32 m[16] = {q0.x, q0.y, q0.z, q0.w, q1.x, q1.y, q1.z, q1.w,
                   q2.x, q2.y, q2.z, q2.w, q3.x, q3.y, q3.z, q3.w};
    bool end = b + 1 == n;
    b3u32 fl = (b == 0 ? B3_CHUNK_START : 0u) | (end ? B3_CHUNK_END | root : 0u);
    b3_compress(cv, m, c, end ? blen : 64u, fl);
  }
}

B3_FN void cv_copy(b3u32 *d, const b3u32 *s) {
  for (int i = 0; i < 8; i++) d[i] = s[i];
}

// Pushes chunk i's CV (of cnt in this thread) on the stack of complete
// subtrees, as in the reference implementation: merge while i + 1 has
// trailing zeros, except after the last chunk (the fold does those).
B3_FN void push(b3u32 (*st)[8], b3u32 &sd, b3u32 *cv, b3u32 i, b3u32 cnt) {
  for (b3u32 t = i + 1; (t & 1) == 0 && i + 1 < cnt; t >>= 1) {
    b3u32 r[8];
    cv_copy(r, cv);
    sd--;
    b3_parent(cv, st[sd], r, 0u);
  }
  cv_copy(st[sd], cv);
  sd++;
}

// Folds the CVs of lanes 0..c-1 into lane 0, pairing level by level; the
// merge that leaves one node takes ROOT when the dispatch is whole. Every
// lane of the warp must call it: the shuffles name all 32.
B3_FN void warp_fold(b3u32 *cv, b3u32 lane, b3u32 c, bool whole) {
  for (b3u32 s = 1; s < 32; s <<= 1) {
    b3u32 r[8];
    for (int i = 0; i < 8; i++) r[i] = __shfl_down_sync(0xffffffffu, cv[i], s);
    if ((lane & (2 * s - 1)) == 0 && lane + s < c) {
      b3u32 l[8];
      cv_copy(l, cv);
      b3_parent(cv, l, r, whole && lane == 0 && c <= 2 * s ? B3_ROOT : 0u);
    }
  }
}

template <b3u32 K>
__global__ void leaf(const uint4 *__restrict__ in, b3u32 *out, Span sp) {
  b3u32 tid = blockIdx.x * blockDim.x + threadIdx.x;
  b3u32 lane = threadIdx.x & 31;
  b3u32 nth = (sp.nch + K - 1) / K;
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
      chunk_cv(cv, in, c, nb, bl, solo && sp.nch == 1 ? B3_ROOT : 0u);
      push(st, sd, cv, i, cnt);
    }
    // A partial run (the input's tail) folds what is left right to left.
    sd--;
    cv_copy(cv, st[sd]);
    while (sd > 0) {
      b3u32 r[8];
      cv_copy(r, cv);
      sd--;
      b3_parent(cv, st[sd], r, solo && sd == 0 ? B3_ROOT : 0u);
    }
  }
  b3u32 base = tid - lane;
  b3u32 c = base < nth ? min(32u, nth - base) : 0u;
  warp_fold(cv, lane, c, sp.whole != 0);
  if (lane == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(tid >> 5) * 8 + i] = cv[i];
}

__global__ void merge(const b3u32 *__restrict__ in, b3u32 *out, Span sp) {
  b3u32 tid = blockIdx.x * blockDim.x + threadIdx.x;
  b3u32 lane = threadIdx.x & 31;
  b3u32 cv[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  if (tid < sp.n)
    for (int i = 0; i < 8; i++) cv[i] = in[tid * 8 + i];
  b3u32 base = tid - lane;
  b3u32 c = base < sp.n ? min(32u, sp.n - base) : 0u;
  warp_fold(cv, lane, c, sp.whole != 0);
  if (lane == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(tid >> 5) * 8 + i] = cv[i];
}

template __global__ void leaf<1>(const uint4 *__restrict__, b3u32 *, Span);
template __global__ void leaf<4>(const uint4 *__restrict__, b3u32 *, Span);
template __global__ void leaf<16>(const uint4 *__restrict__, b3u32 *, Span);
template __global__ void leaf<64>(const uint4 *__restrict__, b3u32 *, Span);
