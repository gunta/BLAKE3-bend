// BLAKE3 compression for the native GPU references: one header that builds
// as Metal (MSL), CUDA and plain C, so the Metal kernel, the CUDA kernel and
// the CPU self-test (cpu_test.c) run the same code.
//
// The state lives in 16 scalars and the block in 16 more; every round is
// written out with its own message indices (MSG_SCHEDULE in ../../c), so no
// permutation runs and the compiler keeps everything in registers.
#ifndef B3CORE_H
#define B3CORE_H

#if defined(__METAL_VERSION__)
#include <metal_stdlib>
#define B3_FN inline
#define B3_THR thread
#define B3_ROTR(x, n) metal::rotate((x), 32u - (n))
typedef uint b3u32;
#elif defined(__CUDACC__) || defined(__CUDA__)  // nvcc, clang
#define B3_FN __device__ __forceinline__
#define B3_THR
#define B3_ROTR(x, n) __funnelshift_r((x), (x), (n))
typedef unsigned int b3u32;
#else
#define B3_FN static inline
#define B3_THR
#define B3_ROTR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
typedef unsigned int b3u32;
#endif

#define B3_CHUNK_START 1u
#define B3_CHUNK_END 2u
#define B3_PARENT 4u
#define B3_ROOT 8u

#define B3_IV0 0x6A09E667u
#define B3_IV1 0xBB67AE85u
#define B3_IV2 0x3C6EF372u
#define B3_IV3 0xA54FF53Au
#define B3_IV4 0x510E527Fu
#define B3_IV5 0x9B05688Cu
#define B3_IV6 0x1F83D9ABu
#define B3_IV7 0x5BE0CD19u

#define B3_G(a, b, c, d, x, y)                                                 \
  a = a + b + (x); d = B3_ROTR(d ^ a, 16); c = c + d; b = B3_ROTR(b ^ c, 12);  \
  a = a + b + (y); d = B3_ROTR(d ^ a, 8);  c = c + d; b = B3_ROTR(b ^ c, 7);

#define B3_ROUND(m, s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12,   \
                 s13, s14, s15)                                                \
  B3_G(v0, v4, v8, v12, m[s0], m[s1])                                          \
  B3_G(v1, v5, v9, v13, m[s2], m[s3])                                          \
  B3_G(v2, v6, v10, v14, m[s4], m[s5])                                         \
  B3_G(v3, v7, v11, v15, m[s6], m[s7])                                         \
  B3_G(v0, v5, v10, v15, m[s8], m[s9])                                         \
  B3_G(v1, v6, v11, v12, m[s10], m[s11])                                       \
  B3_G(v2, v7, v8, v13, m[s12], m[s13])                                        \
  B3_G(v3, v4, v9, v14, m[s14], m[s15])

// cv <- the first 8 words of compress(cv, m, counter t, blen, flags).
B3_FN void b3_compress(B3_THR b3u32 *cv, B3_THR const b3u32 *m, b3u32 t,
                       b3u32 blen, b3u32 flags) {
  b3u32 v0 = cv[0], v1 = cv[1], v2 = cv[2], v3 = cv[3];
  b3u32 v4 = cv[4], v5 = cv[5], v6 = cv[6], v7 = cv[7];
  b3u32 v8 = B3_IV0, v9 = B3_IV1, v10 = B3_IV2, v11 = B3_IV3;
  b3u32 v12 = t, v13 = 0, v14 = blen, v15 = flags;
  B3_ROUND(m, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
  B3_ROUND(m, 2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8)
  B3_ROUND(m, 3, 4, 10, 12, 13, 2, 7, 14, 6, 5, 9, 0, 11, 15, 8, 1)
  B3_ROUND(m, 10, 7, 12, 9, 14, 3, 13, 15, 4, 0, 11, 2, 5, 8, 1, 6)
  B3_ROUND(m, 12, 13, 9, 11, 15, 10, 14, 8, 7, 2, 5, 3, 0, 1, 6, 4)
  B3_ROUND(m, 9, 14, 11, 5, 8, 12, 15, 1, 13, 3, 0, 10, 2, 6, 4, 7)
  B3_ROUND(m, 11, 15, 5, 0, 1, 9, 8, 6, 14, 10, 2, 12, 3, 4, 7, 13)
  cv[0] = v0 ^ v8;  cv[1] = v1 ^ v9;  cv[2] = v2 ^ v10; cv[3] = v3 ^ v11;
  cv[4] = v4 ^ v12; cv[5] = v5 ^ v13; cv[6] = v6 ^ v14; cv[7] = v7 ^ v15;
}

B3_FN void b3_iv(B3_THR b3u32 *cv) {
  cv[0] = B3_IV0; cv[1] = B3_IV1; cv[2] = B3_IV2; cv[3] = B3_IV3;
  cv[4] = B3_IV4; cv[5] = B3_IV5; cv[6] = B3_IV6; cv[7] = B3_IV7;
}

// cv <- parent(l, r): l and r are the two children's CVs.
B3_FN void b3_parent(B3_THR b3u32 *cv, B3_THR const b3u32 *l,
                     B3_THR const b3u32 *r, b3u32 flags) {
  b3u32 m[16];
  for (int i = 0; i < 8; i++) { m[i] = l[i]; m[8 + i] = r[i]; }
  b3_iv(cv);
  b3_compress(cv, m, 0, 64, B3_PARENT | flags);
}

// The tree
// --------
// BLAKE3's tree is left-full: the left side of a node over n chunks holds
// the largest power of two below n. Pairing a level's nodes (0,1), (2,3), ...
// and carrying an odd last node up unchanged builds the same tree, so a GPU
// can reduce level by level. Over a group of 2^k aligned nodes of which the
// first c exist, node j of level L (lane j << L) merges with its right
// neighbour iff (j + 1) << L < c, and the merge is the root iff it leaves a
// single node of the whole input.

#endif
