// Eng.next / Eng.done
// ===================
//
// The engine's C side, in the same file as the Bend runtime. A caller hands
// b3e_hash a list of spans; they become jobs on a queue, and the caller
// sleeps until all are done. Eng.next (on the engine's own thread) takes
// the next job and answers its spans to Bend as Array<U32> terms; Eng.done
// copies the CVs out and wakes the caller.
//
// A span's bytes reach Bend in one of two ways. If they lie inside the
// window a Term can name (the 2^40 words past the heap's base), are
// word-aligned and end on a 64-byte block, the array is the caller's own
// memory: no copy, no fault. Otherwise they are copied into warm heap
// blocks (STAGE of them a job, two sets): while Bend hashes one job, a
// prefetch thread copies the next one's spans into the other set, so the
// copy hides behind the hashing. Either way Bend holds the array through a
// redirect cell that keeps one count of ours, so its last drop never frees
// a block: a free would write a link into the caller's memory, or recycle
// a block we reuse.

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>

#define B3E_SPANS 64  // spans a job, read in place
#define B3E_RESV (16ull << 30)  // the heap's room on macOS (b3e_reserve)
#define B3E_STAGE 2   // spans a job, copied

// The CPU
// -------
//
// A prebuilt engine is compiled for its platform's baseline (ADR 0020), on
// x86-64 the x86-64-v3 of the release binaries: a CPU without AVX2 would
// fault in it. So no code compiled for that baseline runs until
// b3e_cpu_ok says this CPU has every feature the compiler was told to
// assume. The entry points below are compiled for plain x86-64 (B3E_BASE)
// and ask first; the runtime's constructors run from b3e_boot, after the
// check, not at load (patch.py embed). On an older CPU the library loads,
// the engine never starts, and every input is hashed as upstream does.
#if defined(__x86_64__)
#define B3E_BASE __attribute__((target("arch=x86-64")))
#include <cpuid.h>

static B3E_BASE int b3e_cpu_check(void) {
  unsigned a, b, c, d, c1 = 0, b7 = 0, c81 = 0;
  if (!__get_cpuid(1, &a, &b, &c1, &d)) {
    return 0;
  }
  if (__get_cpuid_max(0, NULL) >= 7) {
    __cpuid_count(7, 0, a, b7, c, d);
  }
  if (__get_cpuid_max(0x80000000, NULL) >= 0x80000001) {
    __cpuid(0x80000001, a, b, c81, d);
  }
  unsigned long long xcr0 = 0;
  if (c1 & (1u << 27)) {  // OSXSAVE: the OS saves the vector registers
    unsigned lo, hi;
    __asm__ volatile("xgetbv" : "=a"(lo), "=d"(hi) : "c"(0));
    xcr0 = ((unsigned long long)hi << 32) | lo;
  }
  int ok = 1;
#if defined(__SSE3__)
  ok &= (c1 >> 0) & 1;
#endif
#if defined(__SSSE3__)
  ok &= (c1 >> 9) & 1;
#endif
#if defined(__SSE4_1__)
  ok &= (c1 >> 19) & 1;
#endif
#if defined(__SSE4_2__)
  ok &= (c1 >> 20) & 1;
#endif
#if defined(__POPCNT__)
  ok &= (c1 >> 23) & 1;
#endif
#if defined(__AVX__)
  ok &= (c1 >> 28) & 1 && (xcr0 & 6) == 6;
#endif
#if defined(__FMA__)
  ok &= (c1 >> 12) & 1;
#endif
#if defined(__MOVBE__)
  ok &= (c1 >> 22) & 1;
#endif
#if defined(__F16C__)
  ok &= (c1 >> 29) & 1;
#endif
#if defined(__AVX2__)
  ok &= (b7 >> 5) & 1;
#endif
#if defined(__BMI__)
  ok &= (b7 >> 3) & 1;
#endif
#if defined(__BMI2__)
  ok &= (b7 >> 8) & 1;
#endif
#if defined(__LZCNT__)
  ok &= (c81 >> 5) & 1;
#endif
#if defined(__AVX512F__)
  ok &= (b7 >> 16) & 1;
#if !defined(__APPLE__)
  // macOS turns the AVX-512 state on at a thread's first use, so XCR0 may
  // not show it yet; cpuid's word is the one that counts there
  ok &= (xcr0 & 0xe6) == 0xe6;
#endif
#endif
#if defined(__AVX512DQ__)
  ok &= (b7 >> 17) & 1;
#endif
#if defined(__AVX512CD__)
  ok &= (b7 >> 28) & 1;
#endif
#if defined(__AVX512BW__)
  ok &= (b7 >> 30) & 1;
#endif
#if defined(__AVX512VL__)
  ok &= (b7 >> 31) & 1;
#endif
  return ok;
}
#else
#define B3E_BASE
static int b3e_cpu_check(void) {
  return 1;
}
#endif

// 1 if this CPU runs the engine as compiled; TURBOBLAKE_CPU=0 answers 0, to
// test the path an older CPU takes.
static B3E_BASE int b3e_cpu_ok(void) {
  static int ok = -1;  // a race only computes the same answer twice
  if (ok < 0) {
    const char* force = getenv("TURBOBLAKE_CPU");
    ok = force != NULL && force[0] == '0' ? 0 : b3e_cpu_check();
  }
  return ok;
}

typedef struct B3EJob {
  const unsigned char* p[B3E_SPANS];
  u64 len[B3E_SPANS];  // bytes, at most 1 GiB
  u64 cb[B3E_SPANS];   // chunk counter of the first chunk (both words)
  u32 n;
  u32 key[8];           // the mode: the key words and flag (IV and 0 by default)
  u32 kf;
  unsigned char (*out)[32];
  int* left;            // the caller's count of jobs not done
  int* failed;
  int  set;             // the staging set its copies went to, or -1
  bool ready;           // its copies are in place (prefetched)
  struct B3EJob* next;
} B3EJob;

static pthread_mutex_t b3e_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  b3e_posted = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  b3e_finished = PTHREAD_COND_INITIALIZER;
static B3EJob* b3e_head;  // posted, not yet taken
static B3EJob* b3e_tail;
static B3EJob* b3e_cur;   // taken, being hashed
static u64*    b3e_heap;  // the heap's base, once the engine runs
static int     b3e_state; // 0 not started, 1 running, -1 failed

// A file job: paths for B3IO.take, and where B3IO.give puts each file's
// hash (out) or errno (err). One at a time.
typedef struct {
  const char* const* paths;
  u32  n;
  unsigned char (*out)[32];
  int* err;
  bool done;
} B3EFiles;

static B3EFiles* b3e_fjob;  // posted, not yet taken
static B3EFiles* b3e_fcur;  // taken

// What Eng.next lent Bend for the current job: zero-copy redirect cells to
// release once its CVs are out.
static Term b3e_lent[B3E_SPANS];
static u32  b3e_nlent;

// TURBOBLAKE_TRACE=1 prints these at exit.
static u64 b3e_njobs, b3e_nspans, b3e_ncopied, b3e_bytes, b3e_cbytes, b3e_copy_ns,
  b3e_wait_ns, b3e_hash_ns, b3e_t_next;

static u64 b3e_ns(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (u64)t.tv_sec * 1000000000ull + (u64)t.tv_nsec;
}

static void b3e_report(void) {
  fprintf(stderr, "turboblake: %llu jobs, %llu spans (%llu copied), %llu bytes (%llu copied);"
    " copying %.3f ms (%.3f ms of it waited for), hashing %.3f ms\n",
    (unsigned long long)b3e_njobs, (unsigned long long)b3e_nspans,
    (unsigned long long)b3e_ncopied, (unsigned long long)b3e_bytes,
    (unsigned long long)b3e_cbytes, b3e_copy_ns / 1e6, b3e_wait_ns / 1e6, b3e_hash_ns / 1e6);
}

// Bend can read len bytes at p in place: word-aligned, inside the window
// past the heap's base, and ending on a 64-byte block (Bend reads whole
// blocks, and a short last block's tail must be zeros). On macOS the base
// is known before the engine starts: the heap goes in the room reserved at
// load (b3e_reserve).
#if defined(__APPLE__)
extern char* b3e_resv;
#endif

B3E_BASE int b3e_inside(const void* p, uint64_t len) {
  uintptr_t base = (uintptr_t)b3e_heap, at = (uintptr_t)p;
#if defined(__APPLE__)
  base = base != 0 || b3e_state != 0 ? base : (uintptr_t)b3e_resv;
#endif
  return base != 0 && at % 8 == 0 && len % 64 == 0 && at >= base + HEAP_OFF * 8
      && (at - base) / 8 + (len + 7) / 8 < LOC_MASK;
}

// Copy helpers
// ------------

#define B3E_COPIERS 8

typedef struct {
  char*       dst;
  const char* src;
  u64         len;
} B3ECopy;

static pthread_mutex_t b3e_cmu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  b3e_cgo = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  b3e_cend = PTHREAD_COND_INITIALIZER;
static B3ECopy b3e_cjob;
static u32     b3e_cturn, b3e_cleft, b3e_ncopiers;

static void b3e_copy_part(u32 i, u32 n) {
  u64 per = (b3e_cjob.len / n + 4095) & ~4095ull;
  u64 lo = (u64)i * per, hi = lo + per < b3e_cjob.len ? lo + per : b3e_cjob.len;
  if (lo < hi) {
    memcpy(b3e_cjob.dst + lo, b3e_cjob.src + lo, hi - lo);
  }
}

static void* b3e_copier(void* arg) {
  u32 me = (u32)(uintptr_t)arg, seen = 0;
  for (;;) {
    pthread_mutex_lock(&b3e_cmu);
    while (b3e_cturn == seen) {
      pthread_cond_wait(&b3e_cgo, &b3e_cmu);
    }
    seen = b3e_cturn;
    pthread_mutex_unlock(&b3e_cmu);
    b3e_copy_part(me + 1, b3e_ncopiers + 1);
    pthread_mutex_lock(&b3e_cmu);
    if (--b3e_cleft == 0) {
      pthread_cond_signal(&b3e_cend);
    }
    pthread_mutex_unlock(&b3e_cmu);
  }
  return NULL;
}

// memcpy over the helpers and this thread, zeros to the end of the last
// block; small copies stay on this thread. One copy at a time.
static void b3e_copy(char* dst, const void* src, u64 len) {
  u64 t0 = b3e_ns();
  if (len < (8ull << 20)) {
    memcpy(dst, src, len);
  } else {
    if (b3e_ncopiers == 0) {
      long n = sysconf(_SC_NPROCESSORS_ONLN);
      u32 want = n > 2 ? (u32)(n / 2 < B3E_COPIERS ? n / 2 : B3E_COPIERS) - 1 : 0;
      for (u32 i = 0; i < want; i += 1) {
        pthread_t t;
        if (pthread_create(&t, NULL, b3e_copier, (void*)(uintptr_t)i) == 0) {
          pthread_detach(t);
          b3e_ncopiers += 1;
        }
      }
    }
    pthread_mutex_lock(&b3e_cmu);
    b3e_cjob = (B3ECopy){ dst, src, len };
    b3e_cleft = b3e_ncopiers;
    b3e_cturn += 1;
    pthread_cond_broadcast(&b3e_cgo);
    pthread_mutex_unlock(&b3e_cmu);
    b3e_copy_part(0, b3e_ncopiers + 1);
    pthread_mutex_lock(&b3e_cmu);
    while (b3e_cleft != 0) {
      pthread_cond_wait(&b3e_cend, &b3e_cmu);
    }
    pthread_mutex_unlock(&b3e_cmu);
  }
  memset(dst + len, 0, (64 - len % 64) % 64);
  b3e_copy_ns += b3e_ns() - t0;
}

// Staging
// -------
// Two sets of B3E_STAGE blocks, kept for the engine's life; set s, block k
// holds the k-th copied span of a job.

static Term b3e_stage[2][B3E_STAGE];
static u64  b3e_stage_loc[2][B3E_STAGE];
static u32  b3e_stage_cls[2][B3E_STAGE];

// 2^cls u32 words hold len bytes.
static u32 b3e_cls(u64 len) {
  u64 words = (len + 3) / 4;
  u32 c = 4;
  while ((1ull << c) < words) {
    c += 1;
  }
  return c;
}

// Makes set s big enough for job j's copied spans (engine thread only: it
// allocates on Bend's heap).
static void b3e_room(Env e, B3EJob* j, int s) {
  u32 k = 0;
  for (u32 i = 0; i < j->n; i += 1) {
    if (b3e_inside(j->p[i], j->len[i])) {
      continue;
    }
    u32 cls = b3e_cls(j->len[i]);
    if (b3e_stage[s][k] == 0 || b3e_stage_cls[s][k] < cls) {
      if (b3e_stage[s][k] != 0) {
        term_drop(e, b3e_stage[s][k]);
      }
      u32 c = cls < b3e_cls(16ull << 20) ? b3e_cls(16ull << 20) : cls;
      b3e_stage_loc[s][k] = heap_alloc(e, blk_wcls(0, c));
      b3e_stage[s][k] = term_keep(e, term_blk(0, c, b3e_stage_loc[s][k]), 0);
      b3e_stage_cls[s][k] = c;
    }
    k += 1;
  }
}

// Copies job j's spans that need it into set s.
static void b3e_fill(B3EJob* j, int s) {
  u32 k = 0;
  for (u32 i = 0; i < j->n; i += 1) {
    if (!b3e_inside(j->p[i], j->len[i])) {
      b3e_copy((char*)(b3e_heap + b3e_stage_loc[s][k]), j->p[i], j->len[i]);
      b3e_ncopied += 1;
      b3e_cbytes += j->len[i];
      k += 1;
    }
  }
}

static bool b3e_needs_copy(B3EJob* j) {
  for (u32 i = 0; i < j->n; i += 1) {
    if (!b3e_inside(j->p[i], j->len[i])) {
      return true;
    }
  }
  return false;
}

// The prefetch thread: copies one job ahead, into the set Bend is not
// reading.
static pthread_mutex_t b3e_pmu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  b3e_pgo = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  b3e_pend = PTHREAD_COND_INITIALIZER;
static B3EJob* b3e_pjob;   // being prefetched, or NULL
static bool    b3e_pthread;

static void* b3e_prefetcher(void* arg) {
  for (;;) {
    pthread_mutex_lock(&b3e_pmu);
    while (b3e_pjob == NULL || b3e_pjob->ready) {
      pthread_cond_wait(&b3e_pgo, &b3e_pmu);
    }
    B3EJob* j = b3e_pjob;
    pthread_mutex_unlock(&b3e_pmu);
    b3e_fill(j, j->set);
    pthread_mutex_lock(&b3e_pmu);
    j->ready = true;
    pthread_cond_broadcast(&b3e_pend);
    pthread_mutex_unlock(&b3e_pmu);
  }
  return NULL;
}

static void b3e_prefetch(Env e, B3EJob* j, int s) {
  if (!b3e_pthread) {
    pthread_t t;
    b3e_pthread = pthread_create(&t, NULL, b3e_prefetcher, NULL) == 0;
    if (b3e_pthread) {
      pthread_detach(t);
    }
  }
  b3e_room(e, j, s);
  j->set = s;
  pthread_mutex_lock(&b3e_pmu);
  b3e_pjob = j;
  if (b3e_pthread) {
    pthread_cond_signal(&b3e_pgo);
  }
  pthread_mutex_unlock(&b3e_pmu);
  if (!b3e_pthread) {
    b3e_fill(j, s);
    j->ready = true;
  }
}

// Waits until job j's copies are in place (copying them now if no one is).
static void b3e_ready(Env e, B3EJob* j, int s) {
  u64 t0 = b3e_ns();
  pthread_mutex_lock(&b3e_pmu);
  bool mine = b3e_pjob != j;
  while (!mine && !j->ready) {
    pthread_cond_wait(&b3e_pend, &b3e_pmu);
  }
  if (b3e_pjob == j) {
    b3e_pjob = NULL;
  }
  pthread_mutex_unlock(&b3e_pmu);
  if (mine) {
    b3e_room(e, j, s);
    j->set = s;
    b3e_fill(j, s);
    j->ready = true;
  }
  b3e_wait_ns += b3e_ns() - t0;
}

// Terms
// -----

static Term b3e_ctr(Env e, u64 cid, u32 n, Term* v) {
  u64 l = heap_alloc(e, cls_fit(n));
  for (u32 i = 0; i < n; i += 1) {
    e.mem[l + i] = io_seal(e, v[i], cid);
  }
  return term_ctr(cid, l);
}

// The array for span i: the caller's memory, or block k of j's set.
static Term b3e_arr(Env e, B3EJob* j, u32 i, u32* k) {
  const unsigned char* p = j->p[i];
  u64 len = j->len[i];
  if (b3e_inside(p, len)) {
    Term t = term_keep(e, term_blk(0, b3e_cls(len), ((uintptr_t)p - (uintptr_t)e.mem) / 8), 1);
    b3e_lent[b3e_nlent++] = t;
    return t;
  }
  return term_keep(e, b3e_stage[j->set][(*k)++], 1);
}

static Term b3e_spans(Env e, B3EJob* j, u32 lo, u32 hi, u32* k) {
  if (hi - lo == 1) {
    // bend flattens the key's CV into SpOne: arr, cb, hi (the counter's two
    // words), nch, last, eight key words, kf (14 fields)
    u64 len = j->len[lo], nch = (len + 1023) / 1024;
    Term v[14] = { b3e_arr(e, j, lo, k), (Term)(u32)j->cb[lo], (Term)(u32)(j->cb[lo] >> 32),
      (Term)(u32)nch, (Term)(u32)(len - (nch - 1) * 1024) };
    for (u32 i = 0; i < 8; i += 1) {
      v[5 + i] = (Term)j->key[i];
    }
    v[13] = (Term)j->kf;
    return b3e_ctr(e, CID(SpOne), 14, v);
  }
  u32 mid = lo + (hi - lo) / 2;
  Term l = b3e_spans(e, j, lo, mid, k);
  Term r = b3e_spans(e, j, mid, hi, k);
  Term v[2] = { l, r };
  return b3e_ctr(e, CID(SpTwo), 2, v);
}

// Eng.next: the next job, once a caller posts one. For spans, the copy of
// the job after it starts before Bend sees these.
Term eng_next_run(Env e, Term* f, IoWork* w) {
  static int set;
  pthread_mutex_lock(&b3e_mu);
  b3e_heap = e.mem;
  pthread_cond_broadcast(&b3e_finished);  // b3e_start waits for the first
  while (b3e_head == NULL && b3e_fjob == NULL) {
    pthread_cond_wait(&b3e_posted, &b3e_mu);
  }
  if (b3e_fjob != NULL) {
    b3e_fcur = b3e_fjob;
    b3e_fjob = NULL;
    pthread_mutex_unlock(&b3e_mu);
    return term_pak(CID(JFiles), 0);
  }
  B3EJob* j = b3e_head;
  b3e_head = j->next;
  b3e_tail = b3e_head == NULL ? NULL : b3e_tail;
  B3EJob* after = b3e_head;
  b3e_cur = j;
  pthread_mutex_unlock(&b3e_mu);
  b3e_nlent = 0;
  b3e_njobs += 1;
  b3e_nspans += j->n;
  for (u32 i = 0; i < j->n; i += 1) {
    b3e_bytes += j->len[i];
  }
  if (b3e_needs_copy(j)) {
    b3e_ready(e, j, j->set >= 0 ? j->set : set);
    set = 1 - j->set;
  }
  if (after != NULL && after->set < 0 && b3e_needs_copy(after)) {
    b3e_prefetch(e, after, set);
  }
  u32 k = 0;
  Term t = j->n == 0 ? term_pak(CID(SpNil), 0) : b3e_spans(e, j, 0, j->n, &k);
  b3e_t_next = b3e_ns();
  return b3e_ctr(e, CID(JSpans), 1, &t);
}

// The file job's side of B3IO.take and B3IO.give (b3io.bend, effs/).
const char* const* b3e_file_paths(u32* n) {
  *n = b3e_fcur->n;
  return b3e_fcur->paths;
}

void b3e_file_hash(u32 i, const u64* words) {
  if (i < b3e_fcur->n) {
    for (u32 w = 0; w < 8; w += 1) {
      u32 x = (u32)words[w];
      for (u32 b = 0; b < 4; b += 1) {
        b3e_fcur->out[i][4 * w + b] = (unsigned char)(x >> (8 * b));
      }
    }
    b3e_fcur->err[i] = 0;
  }
}

// The loader reports strerror's text; the caller wants the errno back
// (-1: not a regular file, for the caller to read itself).
void b3e_file_err(u32 i, const char* msg) {
  int code = strcmp(msg, "not a regular file") ? EIO : -1;
  for (int c = 1; c < 256 && code != -1; c += 1) {
    if (!strcmp(strerror(c), msg)) {
      code = c;
      break;
    }
  }
  if (i < b3e_fcur->n) {
    b3e_fcur->err[i] = code;
  }
}

void b3e_files_done(void) {
  pthread_mutex_lock(&b3e_mu);
  b3e_fcur->done = true;
  b3e_fcur = NULL;
  pthread_cond_broadcast(&b3e_finished);
  pthread_mutex_unlock(&b3e_mu);
}

static void b3e_put(Env e, Term c, unsigned char (*out)[32], u32* i) {
  u64 cid = term_aux(c);
  if (cid == CID(CvTwo)) {
    u64 at = term_peek(e.mem, c);
    b3e_put(e, e.mem[at], out, i);
    b3e_put(e, e.mem[at + 1], out, i);
  } else if (cid == CID(CvOne)) {
    // bend flattens the CV into CvOne: eight words; boxed, a pointer to them
    u64 at = term_peek(e.mem, c);
    u64 cv = cid_arity(CID(CvOne)) == 8 ? at : term_peek(e.mem, e.mem[at]);
    for (u32 w = 0; w < 8; w += 1) {
      u32 x = (u32)e.mem[cv + w];
      out[*i][4 * w + 0] = (unsigned char)x;
      out[*i][4 * w + 1] = (unsigned char)(x >> 8);
      out[*i][4 * w + 2] = (unsigned char)(x >> 16);
      out[*i][4 * w + 3] = (unsigned char)(x >> 24);
    }
    *i += 1;
  }
}

// Eng.done: the CVs to the caller; the lent cells back to the heap.
Term eng_done_run(Env e, Term* f, IoWork* w) {
  b3e_hash_ns += b3e_ns() - b3e_t_next;
  B3EJob* j = b3e_cur;
  u32 i = 0;
  b3e_put(e, f[0], j->out, &i);
  term_sink(e, f[0]);
  for (u32 n = 0; n < b3e_nlent; n += 1) {
    // only our count is left: free the cell, never the caller's memory
    u64 r = term_loc(b3e_lent[n]);
    if ((a32_load(a32_at(e.mem, r)) & RFC_CNT) == 1) {
      heap_free(e, 0, r);
    }
  }
  b3e_nlent = 0;
  pthread_mutex_lock(&b3e_mu);
  b3e_cur = NULL;
  if (i != j->n) {
    *j->failed = 1;
  }
  *j->left -= 1;
  pthread_cond_broadcast(&b3e_finished);
  pthread_mutex_unlock(&b3e_mu);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) eng_use(void) {
#ifdef CID(Eng.next)
  io_eff(CID(Eng.next), eng_next_run);
#endif
#ifdef CID(Eng.done)
  io_eff(CID(Eng.done), eng_done_run);
#endif
}

// The caller's side
// -----------------

int b3e_bend_main(int argc, char** argv);  // Bend's main, renamed
#if defined(BEND_EMBED)
static void b3e_ctors(void);  // the runtime's constructors (patch.py embed)
#endif

static pthread_once_t b3e_once = PTHREAD_ONCE_INIT;

// The first big input's address: the heap goes a few TiB below it, so the
// engine's window covers the host's memory (corpus_map, patched).
uintptr_t b3e_hint;

static void* b3e_thread(void* arg) {
  // TURBOBLAKE_THREADS caps the engine's threads (default: every core)
  static char threads[24];
  static char* argv[] = { "turboblake-engine", "+RTS", "--threads", threads, "-RTS", NULL };
  const char* t = getenv("TURBOBLAKE_THREADS");
  if (t != NULL && atoi(t) > 0) {
    snprintf(threads, sizeof threads, "%d", atoi(t));
    b3e_bend_main(5, argv);
  } else {
    b3e_bend_main(1, argv);
  }
  pthread_mutex_lock(&b3e_mu);
  b3e_state = -1;
  pthread_cond_broadcast(&b3e_finished);
  pthread_mutex_unlock(&b3e_mu);
  return NULL;
}

static void b3e_child(void) {
  // a forked child has no engine thread: it hashes in C from now on
  b3e_state = -1;
}

static B3E_BASE void b3e_boot(void) {
  pthread_attr_t a;
  pthread_t t;
  if (!b3e_cpu_ok()) {
    b3e_state = -1;
    return;
  }
#if defined(BEND_EMBED)
  b3e_ctors();
#endif
  if (getenv("TURBOBLAKE_TRACE") != NULL) {
    atexit(b3e_report);
  }
  pthread_attr_init(&a);
  pthread_attr_setstacksize(&a, 64ull << 20);
  pthread_atfork(NULL, NULL, b3e_child);
  if (pthread_create(&t, &a, b3e_thread, NULL) != 0) {
    b3e_state = -1;
    return;
  }
  pthread_detach(t);
  pthread_mutex_lock(&b3e_mu);
  while (b3e_heap == NULL && b3e_state == 0) {
    pthread_cond_wait(&b3e_finished, &b3e_mu);
  }
  if (b3e_state == 0) {
    b3e_state = 1;
  }
  pthread_mutex_unlock(&b3e_mu);
}

#if defined(__APPLE__)
#include <mach/mach.h>
#include <mach/mach_vm.h>

// macOS hands big allocations out from just above a 384 GiB guard (at 448
// GiB), lowest address first, so they sit below any heap placed later, out
// of the engine's window (the 8 TiB past its heap's base), and every span
// was copied. The library reserves its heap's room when it loads, at the
// bottom of that zone: what the host allocates afterwards lands above it,
// inside the window, and the engine reads it where it lies (ADR 0016).
// 16 GiB is what fits under the allocator's own regions; the heap starts
// at 8 and the heaviest jobs measured peak near 5. It cannot grow past it,
// and a Bend heap that runs out ends the process, so b3e_heap_room turns jobs
// away (the caller hashes them as upstream does) well before that.
char* b3e_resv;
u64   b3e_resv_len;

static void __attribute__((constructor)) B3E_BASE b3e_reserve(void) {
  const char* off = getenv("TURBOBLAKE");
  if ((off != NULL && !strcmp(off, "0")) || !b3e_cpu_ok()) {
    return;
  }
  void* p = mmap(NULL, B3E_RESV, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
  if (p == MAP_FAILED) {
    return;
  }
  b3e_resv = p;
  b3e_resv_len = B3E_RESV;
  // The room lands in the lowest hole it fits; a big buffer could still
  // fit a smaller hole below it (libmalloc's regions sit at random places
  // there), out of the window. Those holes get PROT_NONE placeholders, so
  // what the host allocates from now on lands above: 30 processes of 30
  // instead of 7 had every big buffer in the window. A placeholder is
  // mapped by hint, never MAP_FIXED, so it takes nothing another thread
  // mapped meanwhile.
  mach_vm_address_t at = 0, end = 0;
  while (at < (mach_vm_address_t)(uintptr_t)p) {
    mach_vm_size_t size;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t cnt = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t obj;
    if (mach_vm_region(mach_task_self(), &at, &size, VM_REGION_BASIC_INFO_64,
                       (vm_region_info_t)&info, &cnt, &obj) != KERN_SUCCESS) {
      break;
    }
    u64 lo = end, hi = at < (uintptr_t)p ? at : (uintptr_t)p;
    if (lo >= (1ull << 32) && hi > lo && hi - lo >= (64ull << 20)) {
      void* q = mmap((void*)(uintptr_t)lo, hi - lo, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
      if (q != MAP_FAILED && q != (void*)(uintptr_t)lo) {
        munmap(q, hi - lo);
      }
    }
    end = at + size;
    at += size;
  }
}
#endif

// Room on the heap for another job: under 3/4 of a reserved heap used.
static bool b3e_heap_room(void) {
#if defined(__APPLE__)
  if (b3e_resv != NULL && (char*)b3e_heap == b3e_resv) {
    u64 used = (HEAP_OFF + (u64)a32_load(a32_at(b3e_heap, H_BUMP)) * PAGE_LEN) * 8;
    return used < B3E_RESV / 4 * 3;
  }
#endif
  return true;
}

// Starts the engine once; 1 if it runs.
B3E_BASE int b3e_start(void) {
  pthread_once(&b3e_once, b3e_boot);
  return b3e_state == 1;
}

// The heap's base: arrays inside [base, base + 8 TiB) go to Bend uncopied.
B3E_BASE const void* b3e_window(void) {
  return b3e_heap;
}

// 1: spans take whole 64-bit chunk counters, so they may lie past 4 TiB
// (2^32 chunks), each within one 2^32-chunk block. turboblake.c asks
// through a weak reference: an engine built before (a stale prebuilt
// object) has no such symbol and gets counters below 2^32 only.
B3E_BASE int b3e_hi(void) {
  return 1;
}

// Hashes n spans (each at most 1 GiB, none across a multiple of 2^32
// chunks) into out[0..n-1], in the mode of
// key (8 words) and kf: B3E_SPANS a job while they can be read in place,
// B3E_STAGE copied ones a job, every job queued at once. 1 on success, 0 if
// the engine is not running or a span breaks those limits (the caller then
// hashes in C). Bend adds a chunk's index to the span's low counter word
// with no carry into the high one (law span.nocarry), so a span across a
// 2^32-chunk block would hash with wrong counters: it is turned away here.
B3E_BASE int b3e_hash_k(uint32_t n, const unsigned char* const* p, const uint64_t* len,
                        const uint64_t* cb, const uint32_t* key, uint32_t kf,
                        unsigned char (*out)[32]) {
  if (n == 0 || !b3e_cpu_ok() || cid_arity(CID(SpOne)) != 14) {
    return 0;
  }
  for (u32 i = 0; i < n; i += 1) {
    u64 nch = (len[i] + 1023) / 1024;
    if (len[i] > (1ull << 30) || (cb[i] & 0xffffffffull) + nch > (1ull << 32)) {
      return 0;
    }
  }
  if (b3e_hint == 0) {
    b3e_hint = (uintptr_t)p[0];
  }
  if (!b3e_start() || !b3e_heap_room()) {
    return 0;
  }
  B3EJob one;
  B3EJob* jobs = &one;
  u32 cap = 1;
  if (n > 1) {
    cap = n;  // at most one job a span
    jobs = malloc(cap * sizeof(B3EJob));
    if (jobs == NULL) {
      return 0;
    }
  }
  int left = 0, failed = 0;
  u32 nj = 0;
  for (u32 i = 0; i < n;) {
    B3EJob* j = &jobs[nj++];
    j->n = 0;
    j->out = out + i;
    j->left = &left;
    j->failed = &failed;
    j->set = -1;
    j->ready = false;
    j->next = NULL;
    // the builtin: a fortified libc's memcpy is inlined code for the
    // engine's CPU, which this plain x86-64 function cannot take in
    __builtin_memcpy(j->key, key, sizeof j->key);
    j->kf = kf;
    u32 copied = 0;
    while (i < n && j->n < B3E_SPANS) {
      bool copy = !b3e_inside(p[i], len[i]);
      if (copy && copied == B3E_STAGE) {
        break;
      }
      copied += copy;
      j->p[j->n] = p[i];
      j->len[j->n] = len[i];
      j->cb[j->n] = cb[i];
      j->n += 1;
      i += 1;
    }
  }
  pthread_mutex_lock(&b3e_mu);
  left = (int)nj;
  for (u32 k = 0; k < nj; k += 1) {
    if (b3e_tail == NULL) {
      b3e_head = &jobs[k];
    } else {
      b3e_tail->next = &jobs[k];
    }
    b3e_tail = &jobs[k];
  }
  pthread_cond_signal(&b3e_posted);
  while (left > 0 && b3e_state == 1) {
    pthread_cond_wait(&b3e_finished, &b3e_mu);
  }
  pthread_mutex_unlock(&b3e_mu);
  if (jobs != &one) {
    free(jobs);
  }
  return left == 0 && !failed;
}

static pthread_mutex_t b3e_fcall = PTHREAD_MUTEX_INITIALIZER;

// Hashes n files as b3sum.bend does, all at once: out[i] gets file i's
// BLAKE3 hash and err[i] 0; or err[i] its errno, or -1 for a pipe or device
// (the caller reads those itself). 1 on success, 0 if the engine is not
// running.
B3E_BASE int b3e_files(uint32_t n, const char* const* paths, unsigned char (*out)[32], int* err) {
  if (n == 0) {
    return 1;
  }
  if (!b3e_cpu_ok()) {
    return 0;
  }
  if (!b3e_start() || !b3e_heap_room()) {
    return 0;
  }
  B3EFiles j = { paths, n, out, err, false };
  for (u32 i = 0; i < n; i += 1) {
    err[i] = EIO;
  }
  pthread_mutex_lock(&b3e_fcall);
  pthread_mutex_lock(&b3e_mu);
  b3e_fjob = &j;
  pthread_cond_signal(&b3e_posted);
  while (!j.done && b3e_state == 1) {
    pthread_cond_wait(&b3e_finished, &b3e_mu);
  }
  pthread_mutex_unlock(&b3e_mu);
  pthread_mutex_unlock(&b3e_fcall);
  return j.done;
}

static double b3_resident(int fd, u64 len);  // effs/load.c

// Whether the file at path is mostly in the page cache, sampled as the
// loader samples it, without starting the engine: 1 yes, 0 mostly on disk
// (the engine streams such a file), -1 not a regular file or not readable.
// turboblake asks before it starts the engine for one big file.
B3E_BASE int b3e_cached(const char* path) {
  if (!b3e_cpu_ok()) {
    return -1;
  }
  int fd = open(path, O_RDONLY | O_NONBLOCK);
  if (fd < 0) {
    return -1;
  }
  struct stat st;
  int r = fstat(fd, &st) == 0 && S_ISREG(st.st_mode) ? b3_resident(fd, (u64)st.st_size) >= 0.9 : -1;
  close(fd);
  return r;
}

// b3e_hash_k in the default mode.
B3E_BASE int b3e_hash(uint32_t n, const unsigned char* const* p, const uint64_t* len,
                      const uint64_t* cb, unsigned char (*out)[32]) {
  static const uint32_t iv[8] = { 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
                                  0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19 };
  return b3e_hash_k(n, p, len, cb, iv, 0, out);
}
