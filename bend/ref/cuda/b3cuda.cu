// Host for the native CUDA BLAKE3 reference (b3.cu), the twin of
// ../metal/b3metal.m.
//
//   b3cuda vectors [K]               "len hash" per official vector length
//   b3cuda mem <d> <reps> [K]        2^d words of bench/mem.bend's data
//   b3cuda file <path> <reps> [K]    a file, read and copied to the device
//
// K is 1, 4, 16 or 64 chunks per leaf thread (default 4), or 0 for Bend's
// leaf size. mem and file print "us <wall> gpu <gpu> bytes <len> <hash>"
// per run: wall is launch to result on the host, gpu the events around
// the kernels. The input lives in device memory, copied once (file prints
// the copy): a Bend heap on CUDA is managed memory, which faults each page
// across PCIe on the device's first touch instead.
#include <cuda_runtime.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#include "b3.cu"

#define CK(x)                                                                  \
  do {                                                                         \
    cudaError_t e_ = (x);                                                      \
    if (e_ != cudaSuccess) {                                                   \
      fprintf(stderr, "%s: %s\n", #x, cudaGetErrorString(e_));                 \
      exit(1);                                                                 \
    }                                                                          \
  } while (0)

static b3u32 *cv_a, *cv_b;
static const unsigned TPB = 256;

static double now_us(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

// Bend's leaf size for nch chunks (blake3.bend `level`), as b3metal's.
static b3u32 bend_k(b3u32 nch) {
  b3u32 d = 0;
  while ((1u << d) < nch) d++;
  d = d < 14 ? 14 : d > 20 ? 20 : d;
  return 1u << ((d - 14) / 2 * 2);
}

static void launch_leaf(b3u32 k, const uint4 *in, Span s, b3u32 nth) {
  dim3 g((nth + TPB - 1) / TPB), b(TPB);
  switch (k) {
    case 1: leaf<1><<<g, b>>>(in, cv_a, s); break;
    case 4: leaf<4><<<g, b>>>(in, cv_a, s); break;
    case 16: leaf<16><<<g, b>>>(in, cv_a, s); break;
    case 64: leaf<64><<<g, b>>>(in, cv_a, s); break;
    default: fprintf(stderr, "K is 0, 1, 4, 16 or 64\n"); exit(2);
  }
}

// The BLAKE3 hash of len bytes at device pointer in (zero past len to the
// block's end).
static void hash(const uint4 *in, unsigned long long len, b3u32 k, b3u32 out[8],
                 double *wall, double *gpu) {
  b3u32 nch = len == 0 ? 1 : (b3u32)((len + 1023) / 1024);
  b3u32 last = (b3u32)(len - (unsigned long long)(nch - 1) * 1024);
  if (k == 0) k = bend_k(nch);
  static cudaEvent_t e0, e1;
  if (!e0) { CK(cudaEventCreate(&e0)); CK(cudaEventCreate(&e1)); }
  double t0 = now_us();
  CK(cudaEventRecord(e0));
  b3u32 nth = (nch + k - 1) / k;
  Span s = {nch, last, 0, nth <= 32};
  launch_leaf(k, in, s, nth);
  b3u32 *src = cv_a, *dst = cv_b;
  for (b3u32 n = (nth + 31) / 32; n > 1; n = (n + 31) / 32) {
    Span m = {nch, last, n, n <= 32};
    merge<<<(n + TPB - 1) / TPB, TPB>>>(src, dst, m);
    b3u32 *t = src; src = dst; dst = t;
  }
  CK(cudaEventRecord(e1));
  CK(cudaMemcpy(out, src, 32, cudaMemcpyDeviceToHost));
  *wall = now_us() - t0;
  float ms;
  CK(cudaEventElapsedTime(&ms, e0, e1));
  *gpu = ms * 1e3;
  CK(cudaGetLastError());
}

static void hex(const b3u32 cv[8], char s[65]) {
  for (int i = 0; i < 32; i++) sprintf(s + 2 * i, "%02x", (cv[i / 4] >> (8 * (i % 4))) & 0xff);
}

// A device buffer for len bytes, zero to the end of its last chunk.
static uint4 *upload(const void *p, unsigned long long len) {
  unsigned long long sz = (len + 1023) / 1024 * 1024 + 1024;
  void *d;
  CK(cudaMalloc(&d, sz));
  CK(cudaMemset(d, 0, sz));
  if (len) CK(cudaMemcpy(d, p, len, cudaMemcpyHostToDevice));
  return (uint4 *)d;
}

static int vectors(b3u32 k) {
  static const b3u32 lens[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 63, 64, 65, 127, 128, 129,
    1023, 1024, 1025, 2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168,
    7169, 8192, 8193, 16384, 31744, 102400};
  for (size_t i = 0; i < sizeof lens / sizeof *lens; i++) {
    b3u32 n = lens[i];
    unsigned char *p = (unsigned char *)malloc(n + 1);
    for (b3u32 j = 0; j < n; j++) p[j] = (unsigned char)(j % 251);
    uint4 *d = upload(p, n);
    b3u32 cv[8];
    double w, g;
    char h[65];
    hash(d, n, k, cv, &w, &g);
    hex(cv, h);
    printf("%u %s\n", n, h);
    CK(cudaFree(d));
    free(p);
  }
  return 0;
}

static void runs(const uint4 *d, unsigned long long len, int reps, b3u32 k) {
  for (int r = 0; r < reps; r++) {
    b3u32 cv[8];
    double w, g;
    char h[65];
    hash(d, len, k, cv, &w, &g);
    hex(cv, h);
    printf("us %.0f gpu %.0f bytes %llu %s\n", w, g, len, h);
  }
}

static int mem(int d, int reps, b3u32 k) {
  unsigned long long words = 1ull << d, len = words * 4;
  b3u32 *p = (b3u32 *)malloc(len);
  for (unsigned long long j = 0; j < words; j++) p[j] = (b3u32)j * 2654435761u + 12345u;
  uint4 *dv = upload(p, len);
  free(p);
  runs(dv, len, reps, k);
  return 0;
}

static int file(const char *path, int reps, b3u32 k) {
  FILE *f = fopen(path, "rb");
  struct stat st;
  if (!f || stat(path, &st) < 0) { perror(path); return 1; }
  unsigned long long len = (unsigned long long)st.st_size;
  void *p;
  CK(cudaMallocHost(&p, len ? len : 1));
  double t0 = now_us();
  if (len && fread(p, 1, len, f) != len) { perror("read"); return 1; }
  double t1 = now_us();
  uint4 *d = upload(p, len);
  CK(cudaDeviceSynchronize());
  printf("read us %.0f copy us %.0f\n", t1 - t0, now_us() - t1);
  runs(d, len, reps, k);
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: b3cuda vectors|mem|file ...\n"); return 2; }
  // Scratch for the levels: a leaf launch leaves at most nch / 32 CVs.
  CK(cudaMalloc(&cv_a, (1u << 22) * 32));
  CK(cudaMalloc(&cv_b, (1u << 22) * 32));
  if (!strcmp(argv[1], "vectors")) return vectors(argc > 2 ? (b3u32)atoi(argv[2]) : 4);
  if (!strcmp(argv[1], "mem") && argc > 3)
    return mem(atoi(argv[2]), atoi(argv[3]), argc > 4 ? (b3u32)atoi(argv[4]) : 4);
  if (!strcmp(argv[1], "file") && argc > 3)
    return file(argv[2], atoi(argv[3]), argc > 4 ? (b3u32)atoi(argv[4]) : 4);
  fprintf(stderr, "usage: b3cuda vectors|mem|file ...\n");
  return 2;
}
