// libturboblake's GPU backend (ADR 0017)
// =====================================
//
// The hand-written BLAKE3 kernels of bend/ref (ADR 0006, 0013), run by the
// library itself: Metal on macOS, CUDA elsewhere. Nothing is linked: Metal
// is reached through the Objective-C runtime and Metal.framework, opened at
// run time, and CUDA through libcuda's driver API, with the kernels shipped
// as PTX that the driver compiles for whatever GPU it finds. A machine
// without a GPU or a driver, or TURBOBLAKE_GPU=0, leaves tbg_backend() at
// 0, and every caller hashes on the CPU as before.
//
// A job hashes len bytes into the CVs of their 2^glog-chunk groups: one
// leaf dispatch (K chunks a thread, then 2^fold lanes folded), then merges,
// stopping at whole subtrees. The CPU merges those few CVs into the two
// child CVs a subtree hook answers, so every mode and output length is
// finished by the official code, and the GPU never computes a root.
//
// Host memory goes to the GPU only where it reads it in place (a shared
// Metal buffer, CUDA pinned memory: tbg_alloc, tbg_register) and the
// subtree is big; it then splits with the Bend engine, the GPU taking the
// first slices and the engine the rest, at the share their measured rates
// balance. TURBOBLAKE_GPU=all makes the GPU take every subtree, copied to
// it if need be, so the official tests run through the kernels.
//
// Environment:
//   TURBOBLAKE_GPU=0        no GPU
//   TURBOBLAKE_GPU=all      the GPU takes every subtree of 2+ chunks (tests)
//   TURBOBLAKE_GPU_MIN=n    smallest subtree in bytes for the GPU (default 16 MiB,
//                           where the split starts to beat the engine alone)
//   TURBOBLAKE_GPU_SHARE=f  the GPU's share of a split, 0..1 (default: balanced)
//   TURBOBLAKE_GPU_DEVICE=i the CUDA device for host memory (default 0)
//   TURBOBLAKE_TRACE=1      prints the backend and every split

#define _GNU_SOURCE  // clock_gettime, dladdr under -std=c11
#include "turboblake_gpu.h"

#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "b3core.h"
#include "turboblake_kernels.h"  // tbg_metal_src, tbg_ptx (gen_gpu.sh)

// Metal on macOS, CUDA elsewhere (-DTBG_WITH_CUDA builds the CUDA side on a
// Mac, to compile it there).
#if defined(__APPLE__) || defined(__linux__)
#include <dlfcn.h>
#if defined(__APPLE__) && !defined(TBG_WITH_CUDA)
#define TBG_WITH_METAL 1
#else
#undef TBG_WITH_CUDA
#define TBG_WITH_CUDA 1
#endif
#endif

int b3e_hash_k(uint32_t n, const unsigned char *const *p, const uint64_t *len,
               const uint64_t *cb, const uint32_t *key, uint32_t kf,
               unsigned char (*out)[32]);
int b3e_inside(const void *p, uint64_t len);

#define CHUNK 1024ull
#define SPAN_MAX (1ull << 30)
#define SPAN_COPY (64ull << 20)
#define PIECE (64ull << 20)

// The kernels' Span (b3.metal, b3.cu).
typedef struct {
  uint32_t nch, last, n, whole, fold, flags, ctr_lo, ctr_hi, key[8];
} span_t;

static int trace;

static double now_s(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

// A job's dispatches: leaf over K-chunk threads folding 2^f0 lanes, then
// merges folding 2^fm[i] nodes each, so every output CV covers 2^glog
// chunks. K = 4 (the fastest at 1 GiB on both GPUs, ADR 0006) for big
// inputs, else 1, so small ones still spread over many threads.
typedef struct {
  unsigned k, f0, nm, fm[8];
} plan_t;

static plan_t plan(uint64_t nch, unsigned glog) {
  plan_t p = {1, 0, 0, {0}};
  if (glog >= 2 && nch >= (1u << 14)) {
    p.k = 4;
  }
  unsigned rem = glog - (p.k == 4 ? 2 : 0);
  p.f0 = rem < 5 ? rem : 5;
  rem -= p.f0;
  while (rem > 0) {
    p.fm[p.nm] = rem < 5 ? rem : 5;
    rem -= p.fm[p.nm++];
  }
  return p;
}

static uint64_t ceil_div(uint64_t a, uint64_t b) {
  return (a + b - 1) / b;
}

static span_t make_span(uint64_t nch, uint64_t len, const uint32_t key[8], uint8_t flags,
                        uint64_t ctr) {
  span_t s;
  memset(&s, 0, sizeof s);
  s.nch = (uint32_t)nch;
  s.last = (uint32_t)(len - (nch - 1) * CHUNK);
  s.flags = flags;
  s.ctr_lo = (uint32_t)ctr;
  s.ctr_hi = (uint32_t)(ctr >> 32);
  memcpy(s.key, key, 32);
  return s;
}

// Host memory the GPU reads in place
// ---------------------------------
// Each region: its bytes, and how the GPU sees them (a Metal buffer at
// offset 0, or CUDA pinned memory). Few regions live at once, so a list.

typedef struct region {
  uint8_t *p;
  uint64_t len;
  void *buf;      // Metal: the buffer, which starts at base (p or the page below)
  uint8_t *base;
  int owned;      // tbg_alloc'd: freed with the region
  int pinned;     // CUDA: cuMemHostRegister'd by tbg_register
  int refs;
  struct region *next;
} region;

static pthread_mutex_t reg_mu = PTHREAD_MUTEX_INITIALIZER;
static region *regions;

static region *reg_find(const void *p, uint64_t len) {
  for (region *r = regions; r != NULL; r = r->next) {
    if ((const uint8_t *)p >= r->p && (const uint8_t *)p + len <= r->p + r->len) {
      return r;
    }
  }
  return NULL;
}

static void reg_add(uint8_t *p, uint64_t len, void *buf, uint8_t *base, int owned, int pinned) {
  region *r = calloc(1, sizeof *r);
  if (r == NULL) {
    return;
  }
  r->p = p;
  r->len = len;
  r->buf = buf;
  r->base = base;
  r->owned = owned;
  r->pinned = pinned;
  r->refs = 1;
  pthread_mutex_lock(&reg_mu);
  r->next = regions;
  regions = r;
  pthread_mutex_unlock(&reg_mu);
}

// Removes the region starting at p (one reference of it); returns it to
// free when that was the last, else NULL.
static region *reg_take(const void *p) {
  pthread_mutex_lock(&reg_mu);
  region **at = &regions;
  while (*at != NULL && (*at)->p != p) {
    at = &(*at)->next;
  }
  region *r = *at;
  if (r != NULL && --r->refs == 0) {
    *at = r->next;
  } else {
    r = NULL;
  }
  pthread_mutex_unlock(&reg_mu);
  return r;
}

// The job
// -------
// One GPU job at a time per process: gpu_mu is held from start to finish.

static pthread_mutex_t gpu_mu = PTHREAD_MUTEX_INITIALIZER;

typedef struct {
  uint64_t count;  // CVs the job leaves
  double gpu_s;    // the GPU's own time for it
  void *cb;        // Metal: the committed command buffer
  void *res;       // Metal: the buffer holding the CVs
  void *ctx;       // CUDA: the context's state
  void *stream;    // CUDA: the stream it runs on
} job_t;

static job_t job;

static int backend;
static pid_t backend_pid;

#if TBG_WITH_METAL
// Metal, through the Objective-C runtime
// ------------------------------------

typedef struct {
  unsigned long w, h, d;
} mtl_size;

static struct {
  void *(*cls)(const char *);
  void *(*sel)(const char *);
  void (*send)(void);
  void *(*push)(void);
  void (*pop)(void *);
  void *dev, *que, *lib, *leaf1, *leaf4, *merge, *bytes;
  unsigned long tg;
  void *cv[2];
  uint64_t cv_len[2];
  void *stage;
  uint64_t stage_len;
} mt;

#define S(name) mt.sel(name)
#define M(type) ((type)mt.send)
typedef void *(*m0)(void *, void *);
typedef void *(*m1)(void *, void *, void *);
typedef void *(*m2)(void *, void *, void *, void *);
typedef void *(*m3)(void *, void *, void *, void *, void *);
typedef void *(*m_ouu)(void *, void *, unsigned long, unsigned long);
typedef void *(*m_opuuo)(void *, void *, void *, unsigned long, unsigned long, void *);
typedef void *(*m_cpuu)(void *, void *, const void *, unsigned long, unsigned long);
typedef void *(*m_c)(void *, void *, const char *);
typedef void (*v_o)(void *, void *);
typedef void (*v_oo)(void *, void *, void *);
typedef void (*v_ouu)(void *, void *, void *, unsigned long, unsigned long);
typedef void (*v_cuu)(void *, void *, const void *, unsigned long, unsigned long);
typedef void (*v_ss)(void *, void *, mtl_size, mtl_size);
typedef unsigned long (*u_o)(void *, void *);
typedef double (*d_o)(void *, void *);
typedef const char *(*c_o)(void *, void *);

static void mt_release(void *o) {
  if (o != NULL) {
    M(v_o)(o, S("release"));
  }
}

static void mt_err(const char *what, void *err) {
  if (trace) {
    const char *msg = err != NULL
        ? M(c_o)(M(m0)(err, S("localizedDescription")), S("UTF8String")) : "failed";
    fprintf(stderr, "turboblake: metal: %s: %s\n", what, msg);
  }
}

static void *mt_str(const char *s) {
  return M(m_c)(mt.cls("NSString"), S("stringWithUTF8String:"), s);
}

static void *mt_pso(const char *name, int k) {
  void *err = NULL, *f;
  if (k > 0) {
    uint32_t kk = (uint32_t)k, w = 1;
    void *fc = M(m0)(M(m0)(mt.cls("MTLFunctionConstantValues"), S("alloc")), S("init"));
    M(v_cuu)(fc, S("setConstantValue:type:atIndex:"), &kk, 33 /* MTLDataTypeUInt */, 0);
    M(v_cuu)(fc, S("setConstantValue:type:atIndex:"), &w, 33, 1);
    f = M(m3)(mt.lib, S("newFunctionWithName:constantValues:error:"), mt_str(name), fc, &err);
    mt_release(fc);
  } else {
    f = M(m1)(mt.lib, S("newFunctionWithName:"), mt_str(name));
  }
  if (f == NULL) {
    mt_err(name, err);
    return NULL;
  }
  void *p = M(m2)(mt.dev, S("newComputePipelineStateWithFunction:error:"), f, &err);
  mt_release(f);
  if (p == NULL) {
    mt_err(name, err);
    return NULL;
  }
  unsigned long most = M(u_o)(p, S("maxTotalThreadsPerThreadgroup"));
  if (most < mt.tg) {
    mt.tg = most;
  }
  return p;
}

static int mt_init(void) {
  void *objc = dlopen("/usr/lib/libobjc.A.dylib", RTLD_LAZY | RTLD_LOCAL);
  void *mtl = dlopen("/System/Library/Frameworks/Metal.framework/Metal", RTLD_LAZY | RTLD_LOCAL);
  if (objc == NULL || mtl == NULL) {
    return 0;
  }
  mt.cls = (void *(*)(const char *))dlsym(objc, "objc_getClass");
  mt.sel = (void *(*)(const char *))dlsym(objc, "sel_registerName");
  mt.send = (void (*)(void))dlsym(objc, "objc_msgSend");
  mt.push = (void *(*)(void))dlsym(objc, "objc_autoreleasePoolPush");
  mt.pop = (void (*)(void *))dlsym(objc, "objc_autoreleasePoolPop");
  void *(*create)(void) = (void *(*)(void))dlsym(mtl, "MTLCreateSystemDefaultDevice");
  if (!mt.cls || !mt.sel || !mt.send || !mt.push || !mt.pop || !create) {
    return 0;
  }
  void *pool = mt.push();
  int ok = 0;
  double t = now_s();
  mt.dev = create();
  if (mt.dev != NULL) {
    mt.que = M(m0)(mt.dev, S("newCommandQueue"));
    void *src = M(m_cpuu)(M(m0)(mt.cls("NSString"), S("alloc")), S("initWithBytes:length:encoding:"),
                          tbg_metal_src, strlen(tbg_metal_src), 4 /* NSUTF8StringEncoding */);
    void *err = NULL;
    mt.lib = M(m3)(mt.dev, S("newLibraryWithSource:options:error:"), src, NULL, &err);
    mt_release(src);
    if (mt.lib == NULL) {
      mt_err("compile", err);
    } else {
      mt.tg = 256;
      mt.leaf1 = mt_pso("leaf", 1);
      mt.leaf4 = mt_pso("leaf", 4);
      mt.merge = mt_pso("merge", 0);
      mt.bytes = mt_pso("bytes", 0);
      ok = mt.que && mt.leaf1 && mt.leaf4 && mt.merge && mt.bytes;
    }
  }
  if (ok && trace) {
    fprintf(stderr, "turboblake: GPU: Metal, %s (kernels ready in %.0f ms)\n",
            M(c_o)(M(m0)(mt.dev, S("name")), S("UTF8String")), (now_s() - t) * 1e3);
  }
  mt.pop(pool);
  return ok;
}

static void *mt_buffer(uint64_t len) {
  return M(m_ouu)(mt.dev, S("newBufferWithLength:options:"), (unsigned long)len,
                  0 /* MTLResourceStorageModeShared */);
}

// Grows a shared scratch buffer to hold len bytes.
static int mt_grow(void **buf, uint64_t *have, uint64_t len) {
  if (*buf != NULL && *have >= len) {
    return 1;
  }
  uint64_t n = 1u << 16;
  while (n < len) {
    n *= 2;
  }
  mt_release(*buf);
  *buf = mt_buffer(n);
  *have = *buf != NULL ? n : 0;
  return *buf != NULL;
}

static void mt_dispatch(void *enc, void *pso, void *in, uint64_t in_off, void *out,
                        uint64_t out_off, const span_t *s, uint64_t threads) {
  M(v_oo)(enc, S("setComputePipelineState:"), pso);
  M(v_ouu)(enc, S("setBuffer:offset:atIndex:"), in, (unsigned long)in_off, 0);
  M(v_ouu)(enc, S("setBuffer:offset:atIndex:"), out, (unsigned long)out_off, 1);
  M(v_cuu)(enc, S("setBytes:length:atIndex:"), s, sizeof *s, 2);
  mtl_size grid = {(unsigned long)((threads + 31) & ~31ull), 1, 1};
  mtl_size group = {mt.tg, 1, 1};
  M(v_ss)(enc, S("dispatchThreads:threadsPerThreadgroup:"), grid, group);
}

static void *mt_commit(void *cb) {
  M(v_o)(cb, S("commit"));
  return cb;
}

// Waits for cb; 1 if it ran, with its GPU time.
static int mt_wait(void *cb, double *gpu_s) {
  M(v_o)(cb, S("waitUntilCompleted"));
  int ok = M(u_o)(cb, S("status")) == 4;  // MTLCommandBufferStatusCompleted
  if (!ok) {
    mt_err("command buffer", M(m0)(cb, S("error")));
  }
  if (gpu_s != NULL) {
    *gpu_s = M(d_o)(cb, S("GPUEndTime")) - M(d_o)(cb, S("GPUStartTime"));
  }
  mt_release(cb);
  return ok;
}

static void *mt_cmdbuf(void) {
  void *cb = M(m0)(mt.que, S("commandBufferWithUnretainedReferences"));
  return cb != NULL ? M(m0)(cb, S("retain")) : NULL;
}

// Encodes a job over len bytes of buffer `in` at in_off (16-byte aligned).
static int mt_start(void *in, uint64_t in_off, uint64_t len, const uint32_t key[8],
                    uint8_t flags, uint64_t ctr, unsigned glog) {
  uint64_t nch = ceil_div(len, CHUNK);
  plan_t p = plan(nch, glog);
  uint64_t nth = ceil_div(nch, p.k), n1 = ceil_div(nth, 1ull << p.f0);
  if (!mt_grow(&mt.cv[0], &mt.cv_len[0], n1 * 32) || !mt_grow(&mt.cv[1], &mt.cv_len[1], n1 * 32)) {
    return 0;
  }
  void *cb = mt_cmdbuf();
  if (cb == NULL) {
    return 0;
  }
  void *enc = M(m0)(cb, S("computeCommandEncoder"));
  span_t s = make_span(nch, len, key, flags, ctr);
  s.fold = p.f0;
  mt_dispatch(enc, p.k == 4 ? mt.leaf4 : mt.leaf1, in, in_off, mt.cv[0], 0, &s, nth);
  uint64_t nodes = n1;
  int src = 0;
  for (unsigned i = 0; i < p.nm; i += 1) {
    s.n = (uint32_t)nodes;
    s.fold = p.fm[i];
    mt_dispatch(enc, mt.merge, mt.cv[src], 0, mt.cv[1 - src], 0, &s, nodes);
    nodes = ceil_div(nodes, 1ull << p.fm[i]);
    src = 1 - src;
  }
  M(v_o)(enc, S("endEncoding"));
  job.cb = mt_commit(cb);
  job.res = mt.cv[src];
  job.count = nodes;
  return 1;
}

static int mt_finish(uint8_t (*cvs)[32]) {
  int ok = mt_wait(job.cb, &job.gpu_s);
  if (ok) {
    memcpy(cvs, M(m0)(job.res, S("contents")), job.count * 32);
  }
  return ok;
}

static int mt_read(void *buf, uint64_t off, uint64_t len, void *dst) {
  uint64_t have = 0;
  uint8_t *p = tbg_metal_contents(buf, &have);
  if (p != NULL) {
    memcpy(dst, p + off, len);
    return 1;
  }
  // a GPU-only buffer: the bytes kernel copies them to the shared stage
  if (!mt_grow(&mt.stage, &mt.stage_len, len)) {
    return 0;
  }
  void *cb = mt_cmdbuf();
  if (cb == NULL) {
    return 0;
  }
  void *enc = M(m0)(cb, S("computeCommandEncoder"));
  span_t s;
  memset(&s, 0, sizeof s);
  s.n = (uint32_t)len;
  mt_dispatch(enc, mt.bytes, buf, off, mt.stage, 0, &s, len);
  M(v_o)(enc, S("endEncoding"));
  if (!mt_wait(mt_commit(cb), NULL)) {
    return 0;
  }
  memcpy(dst, M(m0)(mt.stage, S("contents")), len);
  return 1;
}
#endif

#if TBG_WITH_CUDA
// CUDA, through libcuda's driver API
// --------------------------------

typedef int CUresult;
typedef int CUdevice;
typedef void *CUcontext, *CUmodule, *CUfunction, *CUstream, *CUevent;
typedef unsigned long long CUdeviceptr;

static struct {
  CUresult (*Init)(unsigned);
  CUresult (*DeviceGetCount)(int *);
  CUresult (*DeviceGet)(CUdevice *, int);
  CUresult (*DeviceGetName)(char *, int, CUdevice);
  CUresult (*DevicePrimaryCtxRetain)(CUcontext *, CUdevice);
  CUresult (*CtxPushCurrent)(CUcontext);
  CUresult (*CtxPopCurrent)(CUcontext *);
  CUresult (*ModuleLoadData)(CUmodule *, const void *);
  CUresult (*ModuleGetFunction)(CUfunction *, CUmodule, const char *);
  CUresult (*MemAlloc)(CUdeviceptr *, size_t);
  CUresult (*MemFree)(CUdeviceptr);
  CUresult (*MemcpyHtoDAsync)(CUdeviceptr, const void *, size_t, CUstream);
  CUresult (*MemcpyDtoHAsync)(void *, CUdeviceptr, size_t, CUstream);
  CUresult (*MemcpyDtoDAsync)(CUdeviceptr, CUdeviceptr, size_t, CUstream);
  CUresult (*LaunchKernel)(CUfunction, unsigned, unsigned, unsigned, unsigned, unsigned,
                           unsigned, unsigned, CUstream, void **, void **);
  CUresult (*StreamCreate)(CUstream *, unsigned);
  CUresult (*StreamSynchronize)(CUstream);
  CUresult (*EventCreate)(CUevent *, unsigned);
  CUresult (*EventRecord)(CUevent, CUstream);
  CUresult (*EventElapsedTime)(float *, CUevent, CUevent);
  CUresult (*PointerGetAttribute)(void *, int, CUdeviceptr);
  CUresult (*MemHostAlloc)(void **, size_t, unsigned);
  CUresult (*MemFreeHost)(void *);
  CUresult (*MemHostRegister)(void *, size_t, unsigned);
  CUresult (*MemHostUnregister)(void *);
  CUresult (*GetErrorString)(CUresult, const char **);
  CUcontext primary;
} cu;

// What the library keeps in each CUDA context it runs in.
typedef struct {
  CUcontext ctx;
  CUmodule mod;
  CUfunction leaf1, leaf4, merge;
  CUdeviceptr cv[2], res, stage;
  uint64_t cv_len[2], res_len, stage_len;
  void *host;  // pinned, for the CVs coming back
  uint64_t host_len;
  CUstream own;
  CUevent e0, e1;
} cu_ctx;

static cu_ctx cuc[8];
static int ncuc;

static int ck(CUresult r, const char *what) {
  if (r != 0 && trace) {
    const char *s = "?";
    if (cu.GetErrorString != NULL) {
      cu.GetErrorString(r, &s);
    }
    fprintf(stderr, "turboblake: cuda: %s: %s (%d)\n", what, s, r);
  }
  return r == 0;
}

static void *cu_sym(void *lib, const char *v2, const char *v1) {
  void *f = v2 != NULL ? dlsym(lib, v2) : NULL;
  return f != NULL ? f : dlsym(lib, v1);
}

// The state for ctx (current on this thread), loading the kernels in it.
static cu_ctx *cu_state(CUcontext ctx) {
  for (int i = 0; i < ncuc; i += 1) {
    if (cuc[i].ctx == ctx) {
      return &cuc[i];
    }
  }
  if (ncuc == 8) {
    return NULL;
  }
  cu_ctx *c = &cuc[ncuc];
  memset(c, 0, sizeof *c);
  c->ctx = ctx;
  double t = now_s();
  if (!ck(cu.ModuleLoadData(&c->mod, tbg_ptx), "load the PTX") ||
      !ck(cu.ModuleGetFunction(&c->leaf1, c->mod, "leaf1"), "leaf1") ||
      !ck(cu.ModuleGetFunction(&c->leaf4, c->mod, "leaf4"), "leaf4") ||
      !ck(cu.ModuleGetFunction(&c->merge, c->mod, "merge"), "merge") ||
      !ck(cu.StreamCreate(&c->own, 1 /* CU_STREAM_NON_BLOCKING */), "stream") ||
      !ck(cu.EventCreate(&c->e0, 0), "event") || !ck(cu.EventCreate(&c->e1, 0), "event")) {
    return NULL;
  }
  if (trace) {
    fprintf(stderr, "turboblake: cuda: kernels loaded in %.0f ms\n", (now_s() - t) * 1e3);
  }
  ncuc += 1;
  return c;
}

static int cu_grow(CUdeviceptr *p, uint64_t *have, uint64_t len) {
  if (*p != 0 && *have >= len) {
    return 1;
  }
  uint64_t n = 1u << 16;
  while (n < len) {
    n *= 2;
  }
  if (*p != 0) {
    cu.MemFree(*p);
  }
  *p = 0;
  *have = 0;
  if (!ck(cu.MemAlloc(p, n), "cuMemAlloc")) {
    return 0;
  }
  *have = n;
  return 1;
}

static int cu_init(void) {
  void *lib = dlopen("libcuda.so.1", RTLD_LAZY | RTLD_LOCAL);
  if (lib == NULL) {
    lib = dlopen("libcuda.so", RTLD_LAZY | RTLD_LOCAL);
  }
  if (lib == NULL) {
    return 0;
  }
#define CU(f, v2, v1) *(void **)&cu.f = cu_sym(lib, v2, v1)
  CU(Init, NULL, "cuInit");
  CU(DeviceGetCount, NULL, "cuDeviceGetCount");
  CU(DeviceGet, NULL, "cuDeviceGet");
  CU(DeviceGetName, NULL, "cuDeviceGetName");
  CU(DevicePrimaryCtxRetain, NULL, "cuDevicePrimaryCtxRetain");
  CU(CtxPushCurrent, "cuCtxPushCurrent_v2", "cuCtxPushCurrent");
  CU(CtxPopCurrent, "cuCtxPopCurrent_v2", "cuCtxPopCurrent");
  CU(ModuleLoadData, NULL, "cuModuleLoadData");
  CU(ModuleGetFunction, NULL, "cuModuleGetFunction");
  CU(MemAlloc, "cuMemAlloc_v2", "cuMemAlloc");
  CU(MemFree, "cuMemFree_v2", "cuMemFree");
  CU(MemcpyHtoDAsync, "cuMemcpyHtoDAsync_v2", "cuMemcpyHtoDAsync");
  CU(MemcpyDtoHAsync, "cuMemcpyDtoHAsync_v2", "cuMemcpyDtoHAsync");
  CU(MemcpyDtoDAsync, "cuMemcpyDtoDAsync_v2", "cuMemcpyDtoDAsync");
  CU(LaunchKernel, NULL, "cuLaunchKernel");
  CU(StreamCreate, NULL, "cuStreamCreate");
  CU(StreamSynchronize, NULL, "cuStreamSynchronize");
  CU(EventCreate, NULL, "cuEventCreate");
  CU(EventRecord, NULL, "cuEventRecord");
  CU(EventElapsedTime, NULL, "cuEventElapsedTime");
  CU(PointerGetAttribute, NULL, "cuPointerGetAttribute");
  CU(MemHostAlloc, NULL, "cuMemHostAlloc");
  CU(MemFreeHost, NULL, "cuMemFreeHost");
  CU(MemHostRegister, "cuMemHostRegister_v2", "cuMemHostRegister");
  CU(MemHostUnregister, NULL, "cuMemHostUnregister");
  CU(GetErrorString, NULL, "cuGetErrorString");
#undef CU
  void **f = (void **)&cu;
  for (size_t i = 0; i < offsetof(__typeof__(cu), primary) / sizeof(void *); i += 1) {
    if (f[i] == NULL) {
      return 0;
    }
  }
  int n = 0, dev_i = getenv("TURBOBLAKE_GPU_DEVICE") ? atoi(getenv("TURBOBLAKE_GPU_DEVICE")) : 0;
  CUdevice dev;
  if (cu.Init(0) != 0 || cu.DeviceGetCount(&n) != 0 || n <= dev_i ||
      !ck(cu.DeviceGet(&dev, dev_i), "cuDeviceGet") ||
      !ck(cu.DevicePrimaryCtxRetain(&cu.primary, dev), "primary context")) {
    return 0;
  }
  cu.CtxPushCurrent(cu.primary);
  cu_ctx *c = cu_state(cu.primary);
  CUcontext was;
  cu.CtxPopCurrent(&was);
  if (c == NULL) {
    return 0;
  }
  if (trace) {
    char name[256] = "?";
    cu.DeviceGetName(name, sizeof name, dev);
    fprintf(stderr, "turboblake: GPU: CUDA, %s\n", name);
  }
  return 1;
}

static void cu_launch(cu_ctx *c, CUfunction f, CUdeviceptr in, CUdeviceptr out, span_t *s,
                      uint64_t threads, CUstream st) {
  void *args[] = {&in, &out, s};
  unsigned blocks = (unsigned)ceil_div(threads, 256);
  ck(cu.LaunchKernel(f, blocks, 1, 1, 256, 1, 1, 0, st, args, NULL), "launch");
  (void)c;
}

// The dispatches of one piece: len bytes at device pointer in, its CVs to
// out (device).
static void cu_piece(cu_ctx *c, CUdeviceptr in, uint64_t len, const uint32_t key[8],
                     uint8_t flags, uint64_t ctr, unsigned glog, CUdeviceptr out, CUstream st) {
  uint64_t nch = ceil_div(len, CHUNK);
  plan_t p = plan(nch, glog);
  uint64_t nth = ceil_div(nch, p.k), nodes = ceil_div(nth, 1ull << p.f0);
  span_t s = make_span(nch, len, key, flags, ctr);
  s.fold = p.f0;
  cu_launch(c, p.k == 4 ? c->leaf4 : c->leaf1, in, p.nm == 0 ? out : c->cv[0], &s, nth, st);
  int src = 0;
  for (unsigned i = 0; i < p.nm; i += 1) {
    s.n = (uint32_t)nodes;
    s.fold = p.fm[i];
    cu_launch(c, c->merge, c->cv[src], i + 1 == p.nm ? out : c->cv[1 - src], &s, nodes, st);
    nodes = ceil_div(nodes, 1ull << p.fm[i]);
    src = 1 - src;
  }
}

// Starts a job over len bytes: at device pointer dev (when host is NULL),
// or copied from host memory, a piece at a time.
static int cu_start(cu_ctx *c, const uint8_t *host, CUdeviceptr dev, uint64_t len,
                    const uint32_t key[8], uint8_t flags, uint64_t ctr, unsigned glog,
                    CUstream st) {
  uint64_t group = CHUNK << glog;
  uint64_t count = ceil_div(len, group);
  int copy = host != NULL || (dev & 15) != 0;
  uint64_t piece = copy ? (PIECE > group ? PIECE : group) : len;
  uint64_t nch_piece = ceil_div(piece < len ? piece : len, CHUNK);
  plan_t p = plan(nch_piece, glog);
  uint64_t n1 = ceil_div(ceil_div(nch_piece, p.k), 1ull << p.f0);
  if (!cu_grow(&c->cv[0], &c->cv_len[0], n1 * 32) || !cu_grow(&c->cv[1], &c->cv_len[1], n1 * 32) ||
      !cu_grow(&c->res, &c->res_len, count * 32) ||
      (copy && !cu_grow(&c->stage, &c->stage_len, piece))) {
    return 0;
  }
  ck(cu.EventRecord(c->e0, st), "event");
  for (uint64_t at = 0; at < len; at += piece) {
    uint64_t n = len - at < piece ? len - at : piece;
    CUdeviceptr in = dev + at;
    if (host != NULL) {
      if (!ck(cu.MemcpyHtoDAsync(c->stage, host + at, n, st), "copy to the GPU")) {
        return 0;
      }
      in = c->stage;
    } else if (copy) {
      if (!ck(cu.MemcpyDtoDAsync(c->stage, dev + at, n, st), "copy on the GPU")) {
        return 0;
      }
      in = c->stage;
    }
    cu_piece(c, in, n, key, flags, ctr + at / CHUNK, glog, c->res + at / group * 32, st);
  }
  ck(cu.EventRecord(c->e1, st), "event");
  job.ctx = c;
  job.stream = st;
  job.count = count;
  return 1;
}

static int cu_finish(uint8_t (*cvs)[32]) {
  cu_ctx *c = job.ctx;
  uint64_t n = job.count * 32;
  if (c->host_len < n) {
    if (c->host != NULL) {
      cu.MemFreeHost(c->host);
    }
    c->host = NULL;
    c->host_len = 0;
    if (!ck(cu.MemHostAlloc(&c->host, n < 65536 ? 65536 : n, 0), "pinned CVs")) {
      return 0;
    }
    c->host_len = n < 65536 ? 65536 : n;
  }
  int ok = ck(cu.MemcpyDtoHAsync(c->host, c->res, n, job.stream), "CVs back") &&
           ck(cu.StreamSynchronize(job.stream), "sync");
  float ms = 0;
  if (ok && cu.EventElapsedTime(&ms, c->e0, c->e1) == 0) {
    job.gpu_s = ms * 1e-3;
  }
  if (ok) {
    memcpy(cvs, c->host, n);
  }
  return ok;
}

// The context a device pointer lives in (made current), or the primary one.
static cu_ctx *cu_enter(CUdeviceptr dev) {
  CUcontext ctx = NULL;
  if (dev == 0 || cu.PointerGetAttribute(&ctx, 1 /* CU_POINTER_ATTRIBUTE_CONTEXT */, dev) != 0 ||
      ctx == NULL) {
    ctx = cu.primary;
  }
  if (!ck(cu.CtxPushCurrent(ctx), "context")) {
    return NULL;
  }
  cu_ctx *c = cu_state(ctx);
  if (c == NULL) {
    CUcontext was;
    cu.CtxPopCurrent(&was);
  }
  return c;
}

static void cu_leave(void) {
  CUcontext was;
  cu.CtxPopCurrent(&was);
}
#endif

// Loading
// -------

static int gpu_off, gpu_all, gpu_min_set, engine_off;
static uint64_t gpu_min = 16ull << 20;
static double gpu_share = -1;

static void read_env(void) {
  trace = getenv("TURBOBLAKE_TRACE") != NULL;
  const char *g = getenv("TURBOBLAKE_GPU");
  gpu_off = g != NULL && !strcmp(g, "0");
  gpu_all = g != NULL && !strcmp(g, "all");
  const char *m = getenv("TURBOBLAKE_GPU_MIN");
  if (m != NULL && atoll(m) >= (long long)(2 * CHUNK)) {
    gpu_min = (uint64_t)atoll(m);
    gpu_min_set = 1;
  }
  const char *s = getenv("TURBOBLAKE_GPU_SHARE");
  if (s != NULL) {
    gpu_share = atof(s);
  }
  const char *e = getenv("TURBOBLAKE");
  engine_off = e != NULL && !strcmp(e, "0");
}

static void env(void) {
  static pthread_once_t once = PTHREAD_ONCE_INIT;
  pthread_once(&once, read_env);
}

static void load(void) {
  env();
  if (gpu_off) {
    return;
  }
#if TBG_WITH_METAL
  backend = mt_init() ? 1 : 0;
#elif TBG_WITH_CUDA
  backend = cu_init() ? 2 : 0;
#endif
  backend_pid = getpid();
}

int tbg_backend(void) {
  static pthread_once_t once = PTHREAD_ONCE_INIT;
  pthread_once(&once, load);
  return backend != 0 && getpid() == backend_pid ? backend : 0;
}

// Jobs
// ----

// Starts a job over len bytes at (kind, obj, off) with gpu_mu held: the
// CVs of its 2^glog-chunk groups. Host bytes must be in a region (read in
// place) unless copy is set.
static int start(int kind, void *obj, uint64_t off, uint64_t len, void *stream,
                 const uint32_t key[8], uint8_t flags, uint64_t ctr, unsigned glog, int copy) {
  memset(&job, 0, sizeof job);
#if TBG_WITH_METAL
  void *pool = mt.push();
  int ok = 0;
  void *buf = obj;
  if (kind == TBG_HOST) {
    const uint8_t *src = (const uint8_t *)obj + off;
    pthread_mutex_lock(&reg_mu);
    region *r = reg_find(src, len);
    buf = r != NULL ? r->buf : NULL;
    off = r != NULL ? (uint64_t)(src - r->base) : 0;
    pthread_mutex_unlock(&reg_mu);
    if ((buf == NULL || off % 16 != 0) && copy && mt_grow(&mt.stage, &mt.stage_len, len)) {
      memcpy(M(m0)(mt.stage, S("contents")), src, len);
      buf = mt.stage;
      off = 0;
    }
    ok = buf != NULL && off % 16 == 0;
  } else {
    // a Metal buffer: off must be 16-byte aligned for the leaf's loads
    ok = 1;
    if (off % 16 != 0) {
      ok = mt_grow(&mt.stage, &mt.stage_len, len);
      if (ok) {
        void *cb = mt_cmdbuf();
        void *enc = M(m0)(cb, S("computeCommandEncoder"));
        span_t s;
        memset(&s, 0, sizeof s);
        s.n = (uint32_t)len;
        mt_dispatch(enc, mt.bytes, buf, off, mt.stage, 0, &s, len);
        M(v_o)(enc, S("endEncoding"));
        ok = mt_wait(mt_commit(cb), NULL);
        buf = mt.stage;
        off = 0;
      }
    }
  }
  ok = ok && mt_start(buf, off, len, key, flags, ctr, glog);
  mt.pop(pool);
  (void)stream;
  return ok;
#elif TBG_WITH_CUDA
  cu_ctx *c = cu_enter(kind == TBG_CUDA ? (CUdeviceptr)(uintptr_t)obj : 0);
  if (c == NULL) {
    return 0;
  }
  int ok;
  if (kind == TBG_CUDA) {
    ok = cu_start(c, NULL, (CUdeviceptr)(uintptr_t)obj + off, len, key, flags, ctr, glog,
                  (CUstream)stream);
  } else {
    pthread_mutex_lock(&reg_mu);
    int pinned = reg_find((uint8_t *)obj + off, len) != NULL;
    pthread_mutex_unlock(&reg_mu);
    ok = (pinned || copy) &&
         cu_start(c, (uint8_t *)obj + off, 0, len, key, flags, ctr, glog, c->own);
  }
  if (!ok) {
    cu_leave();
  }
  return ok;
#else
  (void)kind; (void)obj; (void)off; (void)len; (void)stream; (void)key; (void)flags;
  (void)ctr; (void)glog; (void)copy;
  return 0;
#endif
}

static int finish(uint8_t (*cvs)[32]) {
#if TBG_WITH_METAL
  void *pool = mt.push();
  int ok = mt_finish(cvs);
  mt.pop(pool);
  return ok;
#elif TBG_WITH_CUDA
  int ok = cu_finish(cvs);
  cu_leave();
  return ok;
#else
  (void)cvs;
  return 0;
#endif
}

// Merges n CVs, in place, into cvs[0], as BLAKE3's left-full tree.
static void merge_cvs(const uint32_t key[8], uint8_t flags, uint8_t (*cvs)[32], uint64_t n) {
  if (n < 2) {
    return;
  }
  uint64_t p = 1;
  while (p * 2 <= n - 1) {
    p *= 2;
  }
  merge_cvs(key, flags, cvs, p);
  merge_cvs(key, flags, cvs + p, n - p);
  uint32_t l[8], r[8], cv[8];
  for (int i = 0; i < 8; i += 1) {
    l[i] = (uint32_t)cvs[0][4 * i] | (uint32_t)cvs[0][4 * i + 1] << 8 |
           (uint32_t)cvs[0][4 * i + 2] << 16 | (uint32_t)cvs[0][4 * i + 3] << 24;
    r[i] = (uint32_t)cvs[p][4 * i] | (uint32_t)cvs[p][4 * i + 1] << 8 |
           (uint32_t)cvs[p][4 * i + 2] << 16 | (uint32_t)cvs[p][4 * i + 3] << 24;
  }
  b3_parent(cv, key, l, r, flags);
  for (int i = 0; i < 8; i += 1) {
    for (int b = 0; b < 4; b += 1) {
      cvs[0][4 * i + b] = (uint8_t)(cv[i] >> (8 * b));
    }
  }
}

// BLAKE3's split: the left subtree takes the largest power of two of
// chunks below the total.
static uint64_t left_len(uint64_t len) {
  uint64_t full = (len - 1) / CHUNK, p = 1;
  while (p * 2 <= full) {
    p *= 2;
  }
  return p * CHUNK;
}

static unsigned log2u(uint64_t x) {
  unsigned l = 0;
  while ((1ull << (l + 1)) <= x) {
    l += 1;
  }
  return l;
}

int tbg_dev_subtree(int kind, void *obj, uint64_t off, uint64_t len, void *stream,
                    const uint32_t key[8], uint64_t ctr, uint8_t flags, uint8_t out[64]) {
  if (len <= CHUNK || !tbg_backend() || (kind == TBG_METAL) != (backend == 1) ||
      (kind == TBG_CUDA) != (backend == 2)) {
    return 0;
  }
  // groups as big as the left child: the GPU leaves the two children (its
  // chunk indices are 32-bit, its counters 64-bit)
  uint64_t nch = ceil_div(len, CHUNK);
  if (nch > (1ull << 32)) {
    return 0;
  }
  uint8_t cvs[2][32];
  pthread_mutex_lock(&gpu_mu);
  int ok = start(kind, obj, off, len, stream, key, flags, ctr, log2u(left_len(len) / CHUNK), 0);
  if (ok) {
    ok = finish(cvs);
  }
  pthread_mutex_unlock(&gpu_mu);
  if (ok) {
    memcpy(out, cvs, 64);
  }
  return ok;
}

// The split's balance: each side's rate (bytes a second) from the jobs so
// far, starting from the measured ones (ADR 0017).
static double rate_gpu, rate_cpu;

uint64_t tbg_dev_min(void) {
  env();
  return gpu_min_set ? gpu_min : 64 * CHUNK;
}

int tbg_subtree(const uint8_t *input, uint64_t len, const uint32_t key[8], uint64_t ctr,
                uint8_t flags, uint8_t out[64]) {
  // only memory the GPU was given, or every subtree under TURBOBLAKE_GPU=all:
  // the backend loads no sooner than that
  env();
  if (len <= CHUNK || (!gpu_all && __atomic_load_n(&regions, __ATOMIC_RELAXED) == NULL) ||
      !tbg_backend()) {
    return 0;
  }
  pthread_mutex_lock(&reg_mu);
  int mapped = reg_find(input, len) != NULL;
  pthread_mutex_unlock(&reg_mu);
  if (gpu_all ? len < (gpu_min_set ? gpu_min : 2 * CHUNK) : !mapped || len < gpu_min) {
    return 0;
  }
  uint64_t chunks = ceil_div(len, CHUNK);
  if (chunks > (1ull << 32)) {
    return 0;  // 32-bit chunk indices in the kernels
  }
  // the engine here takes 32-bit chunk counters: past them the GPU takes all
  int wide = ctr + chunks > (1ull << 32);
  // Slices: ~32 to 64 whole subtrees, the GPU taking the first g of them.
  uint64_t left = left_len(len);
  int inside = b3e_inside(input, len - len % 64);
  uint64_t most = inside ? SPAN_MAX : SPAN_COPY;
  uint64_t slice = left / 32 > CHUNK ? left / 32 : CHUNK;
  if (slice > most) {
    slice = most;
  }
  uint64_t n = ceil_div(len, slice), nl = left / slice;
  if (n > (1u << 16)) {
    return 0;
  }
  pthread_mutex_lock(&gpu_mu);
  if (rate_gpu == 0) {
    rate_gpu = backend == 1 ? 150e9 : 40e9;
    rate_cpu = 35e9;
  }
  double r_gpu = rate_gpu, r_cpu = rate_cpu;
  pthread_mutex_unlock(&gpu_mu);
  // On Apple silicon the engine's side pays only when it reads the input in
  // place: copying it spends the memory bandwidth the GPU runs on, and the
  // split loses to the GPU alone (ADR 0017).
  double share = engine_off || wide || (backend == 1 && !inside && gpu_share < 0) ? 1.0
               : gpu_share >= 0 ? gpu_share
               : gpu_all ? 1.0 : r_gpu / (r_gpu + r_cpu);
  uint64_t g = (uint64_t)llround(share * (double)n);
  if (g > n) {
    g = n;
  }
  if (g == 0) {
    return 0;
  }
  uint8_t (*cvs)[32] = malloc(n * 32);
  const unsigned char **p = malloc(n * sizeof *p);
  uint64_t *lens = malloc(n * sizeof *lens), *cb = malloc(n * sizeof *cb);
  int ok = cvs != NULL && p != NULL && lens != NULL && cb != NULL;
  uint64_t gbytes = g * slice < len ? g * slice : len;
  double t0 = now_s(), t_cpu = 0;
  pthread_mutex_lock(&gpu_mu);
  ok = ok && start(TBG_HOST, (void *)input, 0, gbytes, NULL, key, flags, ctr, log2u(slice / CHUNK),
                   gpu_all);
  if (ok && g < n) {
    // the engine takes the rest while the GPU runs
    for (uint64_t i = g; i < n; i += 1) {
      uint64_t at = i * slice;
      p[i - g] = input + at;
      lens[i - g] = len - at < slice ? len - at : slice;
      cb[i - g] = ctr + at / CHUNK;
    }
    double t = now_s();
    int cpu_ok = b3e_hash_k((uint32_t)(n - g), p, lens, cb, key, flags, cvs + g);
    t_cpu = now_s() - t;
    ok = finish(cvs) && cpu_ok;
  } else if (ok) {
    ok = finish(cvs);
  }
  double gpu_s = job.gpu_s;
  if (ok && g < n && gpu_s > 0 && t_cpu > 0) {
    rate_gpu = 0.5 * rate_gpu + 0.5 * ((double)gbytes / gpu_s);
    rate_cpu = 0.5 * rate_cpu + 0.5 * ((double)(len - gbytes) / t_cpu);
  }
  pthread_mutex_unlock(&gpu_mu);
  if (ok) {
    if (trace) {
      fprintf(stderr, "turboblake: split %llu bytes: GPU %llu/%llu slices in %.2f ms, CPU %.2f ms, "
              "all %.2f ms\n", (unsigned long long)len, (unsigned long long)g,
              (unsigned long long)n, gpu_s * 1e3, t_cpu * 1e3, (now_s() - t0) * 1e3);
    }
    merge_cvs(key, flags, cvs, nl);
    merge_cvs(key, flags, cvs + nl, n - nl);
    memcpy(out, cvs[0], 32);
    memcpy(out + 32, cvs[nl], 32);
  }
  free(cvs);
  free(p);
  free(lens);
  free(cb);
  return ok;
}

int tbg_read(int kind, void *obj, uint64_t off, uint64_t len, void *stream, void *dst) {
  if (len == 0) {
    return 1;
  }
  if (!tbg_backend()) {
    return 0;
  }
  int ok = 0;
  pthread_mutex_lock(&gpu_mu);
#if TBG_WITH_METAL
  if (kind == TBG_METAL) {
    void *pool = mt.push();
    ok = mt_read(obj, off, len, dst);
    mt.pop(pool);
  }
#elif TBG_WITH_CUDA
  if (kind == TBG_CUDA) {
    cu_ctx *c = cu_enter((CUdeviceptr)(uintptr_t)obj);
    if (c != NULL) {
      CUstream st = (CUstream)stream;
      ok = ck(cu.MemcpyDtoHAsync(dst, (CUdeviceptr)(uintptr_t)obj + off, len, st), "read") &&
           ck(cu.StreamSynchronize(st), "sync");
      cu_leave();
    }
  }
#endif
  pthread_mutex_unlock(&gpu_mu);
  (void)kind; (void)obj; (void)off; (void)stream; (void)dst;
  return ok;
}

void *tbg_metal_contents(void *buffer, uint64_t *len) {
#if TBG_WITH_METAL
  if (buffer == NULL || tbg_backend() != 1) {
    return NULL;
  }
  void *p = NULL;
  if (M(u_o)(buffer, S("storageMode")) == 0 /* MTLStorageModeShared */) {
    p = M(m0)(buffer, S("contents"));
    *len = M(u_o)(buffer, S("length"));
  }
  return p;
#else
  (void)buffer; (void)len;
  return NULL;
#endif
}

// Host memory the GPU reads
// -------------------------

void *tbg_alloc(size_t len) {
  if (len == 0 || !tbg_backend()) {
    return NULL;
  }
#if TBG_WITH_METAL
  void *pool = mt.push();
  void *buf = mt_buffer(len);
  void *p = buf != NULL ? M(m0)(buf, S("contents")) : NULL;
  mt.pop(pool);
  if (p != NULL) {
    reg_add(p, len, buf, p, 1, 0);
  }
  return p;
#elif TBG_WITH_CUDA
  // pinned memory belongs to a context: the primary one, current meanwhile
  void *p = NULL;
  if (cu_enter(0) == NULL) {
    return NULL;
  }
  int ok = ck(cu.MemHostAlloc(&p, len, 1 /* CU_MEMHOSTALLOC_PORTABLE */), "cuMemHostAlloc");
  cu_leave();
  if (!ok) {
    return NULL;
  }
  reg_add(p, len, NULL, p, 1, 0);
  return p;
#else
  return NULL;
#endif
}

static void reg_free(region *r) {
#if TBG_WITH_METAL
  void *pool = mt.push();
  mt_release(r->buf);
  mt.pop(pool);
#elif TBG_WITH_CUDA
  if ((r->owned || r->pinned) && cu_enter(0) != NULL) {
    if (r->owned) {
      cu.MemFreeHost(r->p);
    } else {
      cu.MemHostUnregister(r->p);
    }
    cu_leave();
  }
#endif
  free(r);
}

void tbg_free(void *p) {
  region *r = p != NULL ? reg_take(p) : NULL;
  if (r != NULL) {
    reg_free(r);
  }
}

int tbg_register(void *p, size_t len) {
  if (p == NULL || len == 0 || !tbg_backend()) {
    return 0;
  }
#if TBG_WITH_METAL
  // a buffer over the whole pages: the region starts at p
  uintptr_t pg = (uintptr_t)getpagesize(), lo = (uintptr_t)p & ~(pg - 1);
  uintptr_t hi = ((uintptr_t)p + len + pg - 1) & ~(pg - 1);
  void *pool = mt.push();
  void *buf = M(m_opuuo)(mt.dev, S("newBufferWithBytesNoCopy:length:options:deallocator:"),
                         (void *)lo, (unsigned long)(hi - lo), 0, NULL);
  mt.pop(pool);
  if (buf == NULL) {
    return 0;
  }
  reg_add(p, len, buf, (uint8_t *)lo, 0, 0);
  return 1;
#elif TBG_WITH_CUDA
  if (cu_enter(0) == NULL) {
    return 0;
  }
  int ok = ck(cu.MemHostRegister(p, len, 1 /* CU_MEMHOSTREGISTER_PORTABLE */), "cuMemHostRegister");
  cu_leave();
  if (!ok) {
    return 0;
  }
  reg_add(p, len, NULL, p, 0, 1);
  return 1;
#else
  return 0;
#endif
}

void tbg_unregister(void *p) {
  tbg_free(p);
}

int tbg_register_metal(void *buffer) {
#if TBG_WITH_METAL
  uint64_t len = 0;
  uint8_t *p = tbg_metal_contents(buffer, &len);
  if (p == NULL) {
    return 0;
  }
  pthread_mutex_lock(&reg_mu);
  region *r = regions;
  while (r != NULL && !(r->p == p && r->buf == buffer)) {
    r = r->next;
  }
  if (r != NULL) {
    r->refs += 1;
  }
  pthread_mutex_unlock(&reg_mu);
  if (r == NULL) {
    void *pool = mt.push();
    M(m0)(buffer, S("retain"));
    mt.pop(pool);
    reg_add(p, len, buffer, p, 0, 0);
  }
  return 1;
#else
  (void)buffer;
  return 0;
#endif
}

// For the tests (cli.c, the Rust crate's): GPU memory holding len bytes of
// p after pad bytes of zeros; on Metal a shared buffer, or a private one
// (gpu_only). Freed with tbg_drop.
void *tbg_upload(const void *p, uint64_t len, uint64_t pad, int gpu_only) {
  if (!tbg_backend()) {
    return NULL;
  }
  void *obj = NULL;
  pthread_mutex_lock(&gpu_mu);
#if TBG_WITH_METAL
  void *pool = mt.push();
  void *shared = mt_buffer(pad + len + 1);
  if (shared != NULL) {
    uint8_t *q = M(m0)(shared, S("contents"));
    memset(q, 0, pad);
    memcpy(q + pad, p, len);
    if (!gpu_only) {
      obj = shared;
    } else {
      obj = M(m_ouu)(mt.dev, S("newBufferWithLength:options:"), (unsigned long)(pad + len + 1),
                     2 << 4 /* MTLResourceStorageModePrivate */);
      void *cb = obj != NULL ? mt_cmdbuf() : NULL;
      if (cb != NULL) {
        void *enc = M(m0)(cb, S("computeCommandEncoder"));
        span_t s;
        memset(&s, 0, sizeof s);
        s.n = (uint32_t)(pad + len + 1);
        mt_dispatch(enc, mt.bytes, shared, 0, obj, 0, &s, pad + len + 1);
        M(v_o)(enc, S("endEncoding"));
        if (!mt_wait(mt_commit(cb), NULL)) {
          mt_release(obj);
          obj = NULL;
        }
      }
      mt_release(shared);
    }
  }
  mt.pop(pool);
#elif TBG_WITH_CUDA
  (void)gpu_only;
  cu_ctx *c = cu_enter(0);
  CUdeviceptr d = 0;
  if (c != NULL) {
    if (ck(cu.MemAlloc(&d, pad + len + 1), "cuMemAlloc")) {
      uint8_t *z = calloc(1, pad + 1);
      int ok = z != NULL && ck(cu.MemcpyHtoDAsync(d, z, pad + 1, c->own), "upload") &&
               ck(cu.MemcpyHtoDAsync(d + pad, p, len, c->own), "upload") &&
               ck(cu.StreamSynchronize(c->own), "sync");
      free(z);
      if (ok) {
        obj = (void *)(uintptr_t)d;
      } else {
        cu.MemFree(d);
      }
    }
    cu_leave();
  }
#else
  (void)p; (void)len; (void)pad; (void)gpu_only;
#endif
  pthread_mutex_unlock(&gpu_mu);
  return obj;
}

void tbg_drop(void *obj) {
  if (obj == NULL || !tbg_backend()) {
    return;
  }
#if TBG_WITH_METAL
  void *pool = mt.push();
  mt_release(obj);
  mt.pop(pool);
#elif TBG_WITH_CUDA
  cu.MemFree((CUdeviceptr)(uintptr_t)obj);
#endif
}
