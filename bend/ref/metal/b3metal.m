// Host for the native Metal BLAKE3 reference (b3.metal).
//
//   b3metal vectors [K]               "len hash" per official vector length
//   b3metal mem <d> <reps> [K] [tg]   2^d words of bench/mem.bend's data
//   b3metal file <path> <reps> [K]    a file, mapped and wrapped with no copy
//   b3metal roof <d> <reps> [K]       the loads alone, the compressions alone
//
// mem and file print "us <wall> gpu <gpu> bytes <len> <hash>" per run: wall
// is encode to completion as the host sees it, gpu the command buffer's
// GPUStartTime..GPUEndTime. The input buffer wraps host memory with no copy
// (unified memory), as a Bend bang reads its heap.
#include <Foundation/Foundation.h>
#include <Metal/Metal.h>
#include <fcntl.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "b3_src.h"  // b3_all_metal: ../b3core.h then b3.metal (build.sh)

// b3.metal's Span: the default mode (the IV, no flags), counters from 0,
// SIMD groups folded whole.
typedef struct { uint32_t nch, last, n, whole, fold, flags, ctr_lo, ctr_hi, key[8]; } Span;

static Span span(uint32_t nch, uint32_t last, uint32_t n, uint32_t whole) {
  Span s = {nch, last, n, whole, 5, 0, 0, 0,
            {0x6A09E667u, 0xBB67AE85u, 0x3C6EF372u, 0xA54FF53Au,
             0x510E527Fu, 0x9B05688Cu, 0x1F83D9ABu, 0x5BE0CD19u}};
  return s;
}

static id<MTLDevice> dev;
static id<MTLCommandQueue> que;
static id<MTLLibrary> lib;
static id<MTLComputePipelineState> merge_pso;
static id<MTLBuffer> cv_a, cv_b;
static NSUInteger tg = 256;

static double now_us(void) {
  static mach_timebase_info_data_t tb;
  if (!tb.denom) mach_timebase_info(&tb);
  return (double)mach_absolute_time() * tb.numer / tb.denom / 1e3;
}

static id<MTLComputePipelineState> pso(NSString *name, MTLFunctionConstantValues *fc) {
  NSError *err = nil;
  id<MTLFunction> f = fc ? [lib newFunctionWithName:name constantValues:fc error:&err]
                         : [lib newFunctionWithName:name];
  if (!f) { fprintf(stderr, "function %s: %s\n", name.UTF8String, err.description.UTF8String); exit(1); }
  id<MTLComputePipelineState> p = [dev newComputePipelineStateWithFunction:f error:&err];
  if (!p) { fprintf(stderr, "pipeline %s: %s\n", name.UTF8String, err.description.UTF8String); exit(1); }
  return p;
}

// W: chunks a leaf thread hashes at once, interleaved (1, 2 or 4; env B3_W).
static uint32_t lane_w = 1;

static id<MTLComputePipelineState> pso_k(NSString *name, uint32_t k) {
  MTLFunctionConstantValues *fc = [MTLFunctionConstantValues new];
  [fc setConstantValue:&k type:MTLDataTypeUInt atIndex:0];
  [fc setConstantValue:&lane_w type:MTLDataTypeUInt atIndex:1];
  return pso(name, fc);
}

static id<MTLComputePipelineState> leaf_pso(uint32_t k) {
  static id<MTLComputePipelineState> cache[256];
  if (!cache[k]) cache[k] = pso_k(@"leaf", k);
  return cache[k];
}

static void setup(void) {
  dev = MTLCreateSystemDefaultDevice();
  if (!dev) { fprintf(stderr, "no Metal device\n"); exit(1); }
  que = [dev newCommandQueue];
  NSString *src = [[NSString alloc] initWithBytes:b3_all_metal length:b3_all_metal_len
                                         encoding:NSUTF8StringEncoding];
  MTLCompileOptions *opt = [MTLCompileOptions new];
  opt.mathMode = MTLMathModeFast;
  // B3_LOAD: wide (default), scalar, coherent or coherent-scalar; B3_CALL=1:
  // chunk compressions as calls (b3.metal).
  const char *ld = getenv("B3_LOAD") ? getenv("B3_LOAD") : "wide";
  opt.preprocessorMacros = @{@"B3_COHERENT" : @(strstr(ld, "coherent") != NULL),
                             @"B3_SCALAR" : @(strstr(ld, "scalar") != NULL),
                             @"B3_CALL" : @(getenv("B3_CALL") && atoi(getenv("B3_CALL")))};
  NSError *err = nil;
  lib = [dev newLibraryWithSource:src options:opt error:&err];
  if (!lib) { fprintf(stderr, "compile: %s\n", err.description.UTF8String); exit(1); }
  merge_pso = pso(@"merge", nil);
  // Scratch for the levels: a leaf dispatch of K >= 1 leaves at most
  // nch / 32 CVs; 2^27 chunks (128 GiB) is far past any input here.
  cv_a = [dev newBufferWithLength:(1u << 22) * 32 options:MTLResourceStorageModeShared];
  cv_b = [dev newBufferWithLength:(1u << 22) * 32 options:MTLResourceStorageModeShared];
}

static void dispatch(id<MTLComputeCommandEncoder> e, id<MTLComputePipelineState> p,
                     id<MTLBuffer> in, id<MTLBuffer> out, Span s, NSUInteger threads) {
  [e setComputePipelineState:p];
  [e setBuffer:in offset:0 atIndex:0];
  [e setBuffer:out offset:0 atIndex:1];
  [e setBytes:&s length:sizeof s atIndex:2];
  NSUInteger t = tg < p.maxTotalThreadsPerThreadgroup ? tg : p.maxTotalThreadsPerThreadgroup;
  [e dispatchThreads:MTLSizeMake((threads + 31) & ~31ul, 1, 1)
      threadsPerThreadgroup:MTLSizeMake(t, 1, 1)];
}

// Bend's leaf size for nch chunks (blake3.bend `level`): 4^j chunks with
// j = floor((clamp(depth, 14, 20) - 14) / 2), about 2^14 leaves, one per
// lane of its 16384-lane cube. K = 0 asks for this shape.
static uint32_t bend_k(uint32_t nch) {
  uint32_t d = 0;
  while ((1u << d) < nch) d++;
  d = d < 14 ? 14 : d > 20 ? 20 : d;
  return 1u << ((d - 14) / 2 * 2);
}

// The BLAKE3 hash of len bytes in `in` (zero past len to the block's end).
static void hash(id<MTLBuffer> in, uint64_t len, uint32_t k, uint32_t out[8],
                 double *wall, double *gpu) {
  uint32_t nch = len == 0 ? 1 : (uint32_t)((len + 1023) / 1024);
  uint32_t last = (uint32_t)(len - (uint64_t)(nch - 1) * 1024);
  if (k == 0) k = bend_k(nch);
  double t0 = now_us();
  id<MTLCommandBuffer> cb = [que commandBufferWithUnretainedReferences];
  id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
  uint32_t nth = (nch + k - 1) / k;
  Span s = span(nch, last, 0, nth <= 32);
  dispatch(e, leaf_pso(k), in, cv_a, s, nth);
  id<MTLBuffer> src = cv_a, dst = cv_b;
  for (uint32_t n = (nth + 31) / 32; n > 1; n = (n + 31) / 32) {
    Span m = span(nch, last, n, n <= 32);
    dispatch(e, merge_pso, src, dst, m, n);
    id<MTLBuffer> t = src; src = dst; dst = t;
  }
  [e endEncoding];
  [cb commit];
  [cb waitUntilCompleted];
  *wall = now_us() - t0;
  *gpu = (cb.GPUEndTime - cb.GPUStartTime) * 1e6;
  if (cb.error) { fprintf(stderr, "gpu: %s\n", cb.error.description.UTF8String); exit(1); }
  memcpy(out, src.contents, 32);
}

static void hex(const uint32_t cv[8], char s[65]) {
  for (int i = 0; i < 32; i++) sprintf(s + 2 * i, "%02x", (cv[i / 4] >> (8 * (i % 4))) & 0xff);
}

static size_t page_up(uint64_t n) {
  size_t pg = (size_t)getpagesize();
  return n == 0 ? pg : (size_t)((n + pg - 1) / pg * pg);
}

static int vectors(uint32_t k) {
  static const uint32_t lens[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 63, 64, 65, 127, 128, 129,
    1023, 1024, 1025, 2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168,
    7169, 8192, 8193, 16384, 31744, 102400};
  for (size_t i = 0; i < sizeof lens / sizeof *lens; i++) {
    uint32_t n = lens[i];
    id<MTLBuffer> b = [dev newBufferWithLength:page_up(n) options:MTLResourceStorageModeShared];
    uint8_t *p = b.contents;
    memset(p, 0, page_up(n));
    for (uint32_t j = 0; j < n; j++) p[j] = (uint8_t)(j % 251);
    uint32_t cv[8];
    double w, g;
    char h[65];
    hash(b, n, k, cv, &w, &g);
    hex(cv, h);
    printf("%u %s\n", n, h);
  }
  return 0;
}

static void runs(id<MTLBuffer> b, uint64_t len, int reps, uint32_t k) {
  for (int r = 0; r < reps; r++) {
    uint32_t cv[8];
    double w, g;
    char h[65];
    hash(b, len, k, cv, &w, &g);
    hex(cv, h);
    printf("us %.0f gpu %.0f bytes %llu %s\n", w, g, (unsigned long long)len, h);
  }
}

static int mem(int d, int reps, uint32_t k) {
  uint64_t words = 1ull << d, len = words * 4;
  size_t sz = page_up(len);
  uint32_t *p = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
  if (p == MAP_FAILED) { perror("mmap"); return 1; }
  for (uint64_t j = 0; j < words; j++) p[j] = (uint32_t)j * 2654435761u + 12345u;
  id<MTLBuffer> b = [dev newBufferWithBytesNoCopy:p length:sz
                                          options:MTLResourceStorageModeShared deallocator:nil];
  runs(b, len, reps, k);
  return 0;
}

// One dispatch of p over nch threads (one per chunk), timed like hash().
static id<MTLBuffer> cells;  // roof_redir's per-thread redirect cells

static uint32_t group = 1;  // roof_group's chunks per group (B3_G)

static void time1(id<MTLComputePipelineState> p, id<MTLBuffer> in, uint32_t nch,
                  uint32_t k, double *wall, double *gpu) {
  double t0 = now_us();
  id<MTLCommandBuffer> cb = [que commandBufferWithUnretainedReferences];
  id<MTLComputeCommandEncoder> e = [cb computeCommandEncoder];
  Span s = span(nch, 1024, group, 0);
  [e setBuffer:cells offset:0 atIndex:3];
  dispatch(e, p, in, cv_a, s, nch / k);
  [e endEncoding];
  [cb commit];
  [cb waitUntilCompleted];
  *wall = now_us() - t0;
  *gpu = (cb.GPUEndTime - cb.GPUStartTime) * 1e6;
}

static int roof(int d, int reps, uint32_t k) {
  uint64_t len = 4ull << d;
  size_t sz = page_up(len);
  uint32_t *p = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
  if (p == MAP_FAILED) { perror("mmap"); return 1; }
  for (uint64_t j = 0; j < len / 4; j++) p[j] = (uint32_t)j * 2654435761u + 12345u;
  id<MTLBuffer> b = [dev newBufferWithBytesNoCopy:p length:sz
                                          options:MTLResourceStorageModeShared deallocator:nil];
  // The same bytes in a buffer Metal allocates itself.
  id<MTLBuffer> own = [dev newBufferWithBytes:p length:sz options:MTLResourceStorageModeShared];
  id<MTLComputePipelineState> rd = pso_k(@"roof_read", k), st = pso_k(@"roof_stride", k),
                              alu = pso_k(@"roof_alu", k), rr = pso_k(@"roof_redir", k),
                              gr = pso_k(@"roof_group", k), gh = pso_k(@"roof_ghash", k);
  if (getenv("B3_G")) group = (uint32_t)atoi(getenv("B3_G"));
  if (group == 0 || k % group != 0) { fprintf(stderr, "B3_G must divide K\n"); return 2; }
  uint32_t nch = (uint32_t)(len / 1024);
  cells = [dev newBufferWithLength:(nch / k) * 8 options:MTLResourceStorageModeShared];
  uint64_t *cp = cells.contents;
  for (uint32_t i = 0; i < nch / k; i++) cp[i] = ((uint64_t)i * k * 256) << 24 | 1;
  for (int r = 0; r < reps; r++) {
    double w1, g1, w2, g2, w3, g3, w4, g4, w5, g5, w6, g6, w7, g7;
    time1(gr, b, nch, k, &w6, &g6);
    time1(gh, b, nch, k, &w7, &g7);
    time1(rd, b, nch, k, &w1, &g1);
    time1(st, b, nch, k, &w3, &g3);
    time1(rd, own, nch, k, &w4, &g4);
    time1(rr, b, nch, k, &w5, &g5);
    time1(alu, b, nch, k, &w2, &g2);
    printf("us: read %.0f  stride %.0f  read-own %.0f  redir %.0f  alu %.0f  group %.0f  ghash %.0f"
           "  K %u  G %u  bytes %llu\n",
           w1, w3, w4, w5, w2, w6, w7, k, group, (unsigned long long)len);
  }
  return 0;
}

static int file(const char *path, int reps, uint32_t k) {
  int fd = open(path, O_RDONLY);
  struct stat st;
  if (fd < 0 || fstat(fd, &st) < 0) { perror(path); return 1; }
  double t0 = now_us();
  size_t sz = page_up((uint64_t)st.st_size);
  void *p = mmap(NULL, sz, PROT_READ, MAP_SHARED, fd, 0);
  if (p == MAP_FAILED) { perror("mmap"); return 1; }
  id<MTLBuffer> b = [dev newBufferWithBytesNoCopy:p length:sz
                                          options:MTLResourceStorageModeShared deallocator:nil];
  if (!b) { fprintf(stderr, "no-copy buffer refused\n"); return 1; }
  printf("map us %.0f\n", now_us() - t0);
  runs(b, (uint64_t)st.st_size, reps, k);
  return 0;
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc < 2) { fprintf(stderr, "usage: b3metal vectors|mem|file ...\n"); return 2; }
    setup();
    if (getenv("B3_W")) lane_w = (uint32_t)atoi(getenv("B3_W"));
    if (lane_w != 1 && lane_w != 2 && lane_w != 4) { fprintf(stderr, "B3_W is 1, 2 or 4\n"); return 2; }
    if (!strcmp(argv[1], "vectors"))
      return vectors(argc > 2 ? (uint32_t)atoi(argv[2]) : 4);
    if (!strcmp(argv[1], "mem") && argc > 3) {
      if (argc > 5) tg = (NSUInteger)atoi(argv[5]);
      return mem(atoi(argv[2]), atoi(argv[3]), argc > 4 ? (uint32_t)atoi(argv[4]) : 4);
    }
    if (!strcmp(argv[1], "roof") && argc > 3)
      return roof(atoi(argv[2]), atoi(argv[3]), argc > 4 ? (uint32_t)atoi(argv[4]) : 1);
    if (!strcmp(argv[1], "file") && argc > 3)
      return file(argv[2], atoi(argv[3]), argc > 4 ? (uint32_t)atoi(argv[4]) : 4);
    fprintf(stderr, "usage: b3metal vectors|mem|file ...\n");
    return 2;
  }
}
