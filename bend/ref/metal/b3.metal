// Native Metal BLAKE3: the reference the Bend GPU path (`hash1!`) races.
// The host prepends ../b3core.h to this file and compiles it at run time.
//
// leaf:  thread t hashes chunks [tK, tK + K), W at a time interleaved (K
//        and W are function constants), folds them with a CV stack, then
//        the 32 lanes of a SIMD group fold their subtrees with shuffles:
//        one CV per 32K chunks.
// merge: one CV per thread, the same SIMD fold: one CV per 32 nodes.
// The host runs leaf once and merge until one node is left.

#include <metal_stdlib>
using namespace metal;

constant uint K [[function_constant(0)]];
constant uint W [[function_constant(1)]];

// How the leaf reads its input (macros from the host, env B3_LOAD): 16-byte
// loads by default; B3_SCALAR reads one word at a time, and B3_COHERENT
// reads through coherent(device) pointers, the way a Bend program reads
// every array of its heap on Metal 3.2+.
#if B3_COHERENT
#define IN_PTR coherent(device) device const
#else
#define IN_PTR device const
#endif

// The 16 words of a block at p into m.
inline void load16(thread uint *m, IN_PTR uint4 *p) {
#if B3_SCALAR
  IN_PTR uint *q = (IN_PTR uint *)p;
  for (int i = 0; i < 16; i++) m[i] = q[i];
#else
  uint4 q0 = p[0], q1 = p[1], q2 = p[2], q3 = p[3];
  m[0] = q0.x;  m[1] = q0.y;  m[2] = q0.z;  m[3] = q0.w;
  m[4] = q1.x;  m[5] = q1.y;  m[6] = q1.z;  m[7] = q1.w;
  m[8] = q2.x;  m[9] = q2.y;  m[10] = q2.z; m[11] = q2.w;
  m[12] = q3.x; m[13] = q3.y; m[14] = q3.z; m[15] = q3.w;
#endif
}

struct Span {
  uint nch;   // chunks in the input
  uint last;  // bytes in the last chunk: 1..1024, 0 for the empty input
  uint n;     // merge: nodes in this level
  uint whole; // this dispatch folds the input to one node (its last merge is ROOT)
};

// B3_CALL compresses the way a Bend program does on the GPU: a long spin
// with several callers is a real call there (DFAR, noinline), and its
// results come back through an array of 64-bit terms in thread memory.
#if B3_CALL
__attribute__((noinline)) void compress_call(thread ulong *o, uint h0, uint h1,
    uint h2, uint h3, uint h4, uint h5, uint h6, uint h7, uint m0, uint m1,
    uint m2, uint m3, uint m4, uint m5, uint m6, uint m7, uint m8, uint m9,
    uint m10, uint m11, uint m12, uint m13, uint m14, uint m15, uint t,
    uint blen, uint flags) {
  uint cv[8] = {h0, h1, h2, h3, h4, h5, h6, h7};
  uint m[16] = {m0, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13, m14, m15};
  b3_compress(cv, m, t, blen, flags);
  for (int i = 0; i < 8; i++) o[i] = cv[i];
}

inline void compress(thread uint *cv, thread const uint *m, uint t, uint blen,
                     uint flags) {
  ulong o[8];
  compress_call(o, cv[0], cv[1], cv[2], cv[3], cv[4], cv[5], cv[6], cv[7], m[0],
                m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10],
                m[11], m[12], m[13], m[14], m[15], t, blen, flags);
  for (int i = 0; i < 8; i++) cv[i] = (uint)o[i];
}
#else
#define compress b3_compress
#endif

// The CV of chunk c (counter c): n blocks, the last of blen bytes.
inline void chunk_cv(thread uint *cv, IN_PTR uint4 *in, uint c, uint n,
                     uint blen, uint root) {
  b3_iv(cv);
  IN_PTR uint4 *p = in + c * 64;
  for (uint b = 0; b < n; b++) {
    uint m[16];
    load16(m, p);
    p += 4;
    bool end = b + 1 == n;
    uint fl = (b == 0 ? B3_CHUNK_START : 0u) | (end ? B3_CHUNK_END | root : 0u);
    compress(cv, m, c, end ? blen : 64u, fl);
  }
}

inline void cv_copy(thread uint *d, thread const uint *s) {
  for (int i = 0; i < 8; i++) d[i] = s[i];
}

// W full chunks from c at once: W independent chains, so a thread keeps W
// blocks' loads in flight instead of one.
inline void chunks_w(thread uint (*cv)[8], IN_PTR uint4 *in, uint c) {
  for (uint j = 0; j < W; j++) b3_iv(cv[j]);
  for (uint b = 0; b < 16; b++) {
    uint m[4][16];
    for (uint j = 0; j < W; j++) load16(m[j], in + (c + j) * 64 + b * 4);
    uint fl = (b == 0 ? B3_CHUNK_START : 0u) | (b == 15 ? B3_CHUNK_END : 0u);
    for (uint j = 0; j < W; j++) compress(cv[j], m[j], c + j, 64, fl);
  }
}

// Pushes chunk i's CV (of cnt in this thread) on the stack of complete
// subtrees, as in the reference implementation: merge while i + 1 has
// trailing zeros, except after the last chunk (the fold does those).
inline void push(thread uint (*st)[8], thread uint &sd, thread uint *cv, uint i,
                 uint cnt) {
  for (uint t = i + 1; (t & 1) == 0 && i + 1 < cnt; t >>= 1) {
    uint r[8];
    cv_copy(r, cv);
    sd--;
    b3_parent(cv, st[sd], r, 0u);
  }
  cv_copy(st[sd], cv);
  sd++;
}

// Folds the CVs of lanes 0..c-1 into lane 0, pairing level by level; the
// merge that leaves one node takes ROOT when the dispatch is whole.
inline void simd_fold(thread uint *cv, uint lane, uint c, bool whole) {
  for (uint s = 1; s < 32; s <<= 1) {
    uint r[8];
    for (int i = 0; i < 8; i++) r[i] = simd_shuffle_down(cv[i], (ushort)s);
    if ((lane & (2 * s - 1)) == 0 && lane + s < c) {
      uint l[8];
      cv_copy(l, cv);
      b3_parent(cv, l, r, whole && lane == 0 && c <= 2 * s ? B3_ROOT : 0u);
    }
  }
}

kernel void leaf(IN_PTR uint4 *in [[buffer(0)]],
                 device uint *out [[buffer(1)]],
                 constant Span &sp [[buffer(2)]],
                 uint tid [[thread_position_in_grid]],
                 uint lane [[thread_index_in_simdgroup]]) {
  uint nth = (sp.nch + K - 1) / K;
  uint cv[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  if (tid < nth) {
    uint c0 = tid * K;
    uint cnt = min(K, sp.nch - c0);
    bool solo = sp.whole && nth == 1;
    uint st[8][8];
    uint sd = 0;
    for (uint i = 0; i < cnt;) {
      if (W > 1 && i + W <= cnt && c0 + i + W < sp.nch) {
        uint cvs[4][8];
        chunks_w(cvs, in, c0 + i);
        for (uint j = 0; j < W; j++, i++) push(st, sd, cvs[j], i, cnt);
      } else {
        uint c = c0 + i;
        bool lastc = c + 1 == sp.nch;
        uint nb = lastc ? max(1u, (sp.last + 63) / 64) : 16u;
        uint bl = lastc ? sp.last - 64 * (nb - 1) : 64u;
        chunk_cv(cv, in, c, nb, bl, solo && sp.nch == 1 ? B3_ROOT : 0u);
        push(st, sd, cv, i, cnt);
        i++;
      }
    }
    // A partial run (the input's tail) folds what is left right to left.
    sd--;
    cv_copy(cv, st[sd]);
    while (sd > 0) {
      uint r[8];
      cv_copy(r, cv);
      sd--;
      b3_parent(cv, st[sd], r, solo && sd == 0 ? B3_ROOT : 0u);
    }
  }
  uint base = tid - lane;
  uint c = base < nth ? min(32u, nth - base) : 0u;
  simd_fold(cv, lane, c, sp.whole != 0);
  if (lane == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(tid >> 5) * 8 + i] = cv[i];
}

kernel void merge(device const uint *in [[buffer(0)]],
                  device uint *out [[buffer(1)]],
                  constant Span &sp [[buffer(2)]],
                  uint tid [[thread_position_in_grid]],
                  uint lane [[thread_index_in_simdgroup]]) {
  uint cv[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  if (tid < sp.n)
    for (int i = 0; i < 8; i++) cv[i] = in[tid * 8 + i];
  uint base = tid - lane;
  uint c = base < sp.n ? min(32u, sp.n - base) : 0u;
  simd_fold(cv, lane, c, sp.whole != 0);
  if (lane == 0 && c > 0)
    for (int i = 0; i < 8; i++) out[(tid >> 5) * 8 + i] = cv[i];
}

// Rooflines, on the leaf's shape (thread t owns chunks [tK, tK + K)):
// roof_read does the loads alone (B3_LOAD applies), roof_alu the 16
// compressions per chunk alone, from registers.
kernel void roof_read(IN_PTR uint4 *in [[buffer(0)]],
                      device uint *out [[buffer(1)]],
                      constant Span &sp [[buffer(2)]],
                      uint tid [[thread_position_in_grid]]) {
  if (tid >= sp.nch / K) return;
  IN_PTR uint4 *p = in + tid * K * 64;
  uint x = 0;
  for (uint b = 0; b < 16 * K; b++) {
    uint m[16];
    load16(m, p + 4 * b);
    for (int i = 0; i < 16; i++) x ^= m[i];
  }
  out[tid] = x;
}

// roof_stride: K chunks per thread like roof_read, but thread t reads
// chunks t, t + T, t + 2T, ... (T threads): the threads running together
// read neighbouring chunks, as K = 1 does.
kernel void roof_stride(IN_PTR uint4 *in [[buffer(0)]],
                        device uint *out [[buffer(1)]],
                        constant Span &sp [[buffer(2)]],
                        uint tid [[thread_position_in_grid]]) {
  uint nth = sp.nch / K;
  if (tid >= nth) return;
  uint x = 0;
  for (uint j = 0; j < K; j++) {
    IN_PTR uint4 *p = in + (tid + j * nth) * 64;
    for (uint b = 0; b < 16; b++) {
      uint m[16];
      load16(m, p + 4 * b);
      for (int i = 0; i < 16; i++) x ^= m[i];
    }
  }
  out[tid] = x;
}

// roof_redir: roof_read through an array handle the way a Bend lane holds
// a forked array, a redirect cell in the heap: every word's address first
// loads the cell (volatile, so nothing hoists it), then the word.
kernel void roof_redir(IN_PTR uint *in [[buffer(0)]],
                       device uint *out [[buffer(1)]],
                       constant Span &sp [[buffer(2)]],
                       volatile coherent(device) device ulong *cell [[buffer(3)]],
                       uint tid [[thread_position_in_grid]]) {
  if (tid >= sp.nch / K) return;
  uint x = 0;
  for (uint w = 0; w < 256 * K; w++) {
    ulong loc = cell[tid] >> 24;
    x ^= in[loc + w];
  }
  out[tid] = x;
}

kernel void roof_alu(device const uint4 *in [[buffer(0)]],
                     device uint *out [[buffer(1)]],
                     constant Span &sp [[buffer(2)]],
                     uint tid [[thread_position_in_grid]]) {
  if (tid >= sp.nch / K) return;
  uint cv[8];
  uint m[16];
  b3_iv(cv);
  for (int i = 0; i < 16; i++) m[i] = tid * 16 + i;
  for (uint b = 0; b < 16 * K; b++) {
    b3_compress(cv, m, tid, 64, b == 0 ? B3_CHUNK_START : 0u);
    m[b] ^= cv[b & 7];
  }
  out[tid] = cv[0];
}

// roof_flat reads the same bytes coalesced: load b of thread t is uint4
// t + b * nch, so a SIMD group's 32 loads are 512 contiguous bytes.
kernel void roof_flat(device const uint4 *in [[buffer(0)]],
                      device uint *out [[buffer(1)]],
                      constant Span &sp [[buffer(2)]],
                      uint tid [[thread_position_in_grid]]) {
  if (tid >= sp.nch) return;
  uint4 x = 0;
  for (uint b = 0; b < 64; b++) x ^= in[tid + b * sp.nch];
  out[tid] = x.x ^ x.y ^ x.z ^ x.w;
}
