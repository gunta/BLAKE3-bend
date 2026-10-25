// Eng.next / Eng.done
// ===================
//
// The engine's C side, in the same file as the Bend runtime: a caller
// thread posts spans with b3e_hash and sleeps; Eng.next (on the engine's
// own thread) wraps them as Array<U32> terms and answers them to Bend;
// Eng.done copies the CVs out and wakes the caller. One job runs at a time.
//
// A span's bytes reach Bend in one of two ways. If they lie inside the
// window a Term can name (the 2^40 words past the heap's base) and are
// word-aligned, the array is the caller's own memory: no copy, no fault.
// Otherwise they are copied, by a few helper threads, into one of two heap
// blocks that are kept across jobs (warm, so the copy pays no page faults).
// Either way Bend holds the array through a redirect cell that keeps one
// count of ours, so its last drop never frees a block: a free would write
// a link into the caller's memory, or recycle a block we reuse.

#include <pthread.h>

#define B3E_SPANS 64
#define B3E_STAGE 2

typedef struct {
  const unsigned char* p[B3E_SPANS];
  u64 len[B3E_SPANS];  // bytes, whole chunks, at most 1 GiB
  u64 cb[B3E_SPANS];   // chunk counter of the first chunk
  u32 n;
  unsigned char (*out)[32];
  u32 copied;          // spans that went through a staging block
  int done;
} B3EJob;

static pthread_mutex_t b3e_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  b3e_posted = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  b3e_finished = PTHREAD_COND_INITIALIZER;
static B3EJob* b3e_job;   // posted, not yet taken
static B3EJob* b3e_cur;   // taken, being hashed
static u64*    b3e_heap;  // the heap's base, once the engine runs

// What Eng.next lent Bend for the current job: zero-copy redirect cells to
// release once its CVs are out.
static Term b3e_lent[B3E_SPANS];
static u32  b3e_nlent;

// BLAKE3_BEND_TRACE=1 prints these at exit.
static u64 b3e_njobs, b3e_nspans, b3e_ncopied, b3e_bytes, b3e_cbytes, b3e_copy_ns, b3e_hash_ns, b3e_t_next;

static u64 b3e_ns(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (u64)t.tv_sec * 1000000000ull + (u64)t.tv_nsec;
}

static void b3e_report(void) {
  fprintf(stderr, "blake3-bend: %llu jobs, %llu spans (%llu copied), %llu bytes (%llu copied);"
    " copying %.3f ms, hashing %.3f ms\n",
    (unsigned long long)b3e_njobs, (unsigned long long)b3e_nspans,
    (unsigned long long)b3e_ncopied, (unsigned long long)b3e_bytes,
    (unsigned long long)b3e_cbytes, b3e_copy_ns / 1e6, b3e_hash_ns / 1e6);
}

static Term b3e_stage[B3E_STAGE];
static u64  b3e_stage_loc[B3E_STAGE];
static u32  b3e_stage_cls[B3E_STAGE];

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

// memcpy over the helpers and this thread; small copies stay on this one.
static void b3e_copy(void* dst, const void* src, u64 len) {
  if (len < (8ull << 20)) {
    memcpy(dst, src, len);
    return;
  }
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

// Terms
// -----

static Term b3e_ctr(Env e, u64 cid, u32 n, Term* v) {
  u64 l = heap_alloc(e, cls_fit(n));
  for (u32 i = 0; i < n; i += 1) {
    e.mem[l + i] = io_seal(e, v[i], cid);
  }
  return term_ctr(cid, l);
}

// 2^cls u32 words hold len bytes.
static u32 b3e_cls(u64 len) {
  u64 words = (len + 3) / 4;
  u32 c = 4;
  while ((1ull << c) < words) {
    c += 1;
  }
  return c;
}

// The array for span i: the caller's memory, or staging block k.
static Term b3e_arr(Env e, B3EJob* j, u32 i, u32* k) {
  const unsigned char* p = j->p[i];
  u64 len = j->len[i];
  u32 cls = b3e_cls(len);
  uintptr_t base = (uintptr_t)e.mem, at = (uintptr_t)p;
  if (at % 8 == 0 && at >= base + HEAP_OFF * 8 && (at - base) / 8 + (len + 7) / 8 < LOC_MASK) {
    Term t = term_keep(e, term_blk(0, cls, (at - base) / 8), 1);
    b3e_lent[b3e_nlent++] = t;
    return t;
  }
  u32 s = (*k)++;
  if (b3e_stage[s] == 0 || b3e_stage_cls[s] < cls) {
    if (b3e_stage[s] != 0) {
      term_drop(e, b3e_stage[s]);
    }
    u32 c = cls < b3e_cls(64ull << 20) ? b3e_cls(64ull << 20) : cls;
    b3e_stage_loc[s] = heap_alloc(e, blk_wcls(0, c));
    b3e_stage[s] = term_keep(e, term_blk(0, c, b3e_stage_loc[s]), 0);
    b3e_stage_cls[s] = c;
  }
  u64 t0 = b3e_ns();
  b3e_copy((char*)(e.mem + b3e_stage_loc[s]), p, len);
  b3e_copy_ns += b3e_ns() - t0;
  j->copied += 1;
  b3e_ncopied += 1;
  b3e_cbytes += len;
  return term_keep(e, b3e_stage[s], 1);
}

static Term b3e_spans(Env e, B3EJob* j, u32 lo, u32 hi, u32* k) {
  if (hi - lo == 1) {
    Term v[3] = { b3e_arr(e, j, lo, k), (Term)(u32)j->cb[lo], (Term)(u32)(j->len[lo] / 1024) };
    return b3e_ctr(e, CID(SpOne), 3, v);
  }
  u32 mid = lo + (hi - lo) / 2;
  Term l = b3e_spans(e, j, lo, mid, k);
  Term r = b3e_spans(e, j, mid, hi, k);
  Term v[2] = { l, r };
  return b3e_ctr(e, CID(SpTwo), 2, v);
}

// Eng.next: the next job's spans, once a caller posts one.
Term eng_next_run(Env e, Term* f, IoWork* w) {
  pthread_mutex_lock(&b3e_mu);
  b3e_heap = e.mem;
  pthread_cond_broadcast(&b3e_finished);  // b3e_start waits for the first
  while (b3e_job == NULL) {
    pthread_cond_wait(&b3e_posted, &b3e_mu);
  }
  B3EJob* j = b3e_job;
  b3e_job = NULL;
  b3e_cur = j;
  pthread_mutex_unlock(&b3e_mu);
  b3e_nlent = 0;
  u32 k = 0;
  b3e_njobs += 1;
  b3e_nspans += j->n;
  for (u32 i = 0; i < j->n; i += 1) {
    b3e_bytes += j->len[i];
  }
  if (j->n == 0) {
    return term_pak(CID(SpNil), 0);
  }
  Term t = b3e_spans(e, j, 0, j->n, &k);
  b3e_t_next = b3e_ns();
  return t;
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
  j->done = i == j->n ? 1 : -1;
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

static pthread_once_t b3e_once = PTHREAD_ONCE_INIT;
static pthread_mutex_t b3e_call = PTHREAD_MUTEX_INITIALIZER;
static int b3e_state;  // 0 not started, 1 running, -1 failed

static void* b3e_thread(void* arg) {
  // BLAKE3_BEND_THREADS caps the engine's threads (default: every core)
  static char threads[24];
  static char* argv[] = { "blake3-bend-engine", "+RTS", "--threads", threads, "-RTS", NULL };
  const char* t = getenv("BLAKE3_BEND_THREADS");
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

static void b3e_boot(void) {
  pthread_attr_t a;
  pthread_t t;
  if (getenv("BLAKE3_BEND_TRACE") != NULL) {
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

// Starts the engine once; 1 if it runs.
int b3e_start(void) {
  pthread_once(&b3e_once, b3e_boot);
  return b3e_state == 1;
}

// The heap's base: arrays inside [base, base + 8 TiB) go to Bend uncopied.
const void* b3e_window(void) {
  return b3e_heap;
}

// Hashes n spans (each whole chunks, at most 1 GiB, at most B3E_STAGE of
// them outside the window) into out[0..n-1]; 1 on success, 0 if the engine
// is not running (the caller then hashes in C).
int b3e_hash(uint32_t n, const unsigned char* const* p, const uint64_t* len,
             const uint64_t* cb, unsigned char (*out)[32]) {
  if (n == 0 || n > B3E_SPANS || !b3e_start()) {
    return 0;
  }
  B3EJob j;
  j.n = n;
  j.out = out;
  for (u32 i = 0; i < n; i += 1) {
    j.p[i] = p[i];
    j.len[i] = len[i];
    j.cb[i] = cb[i];
  }
  pthread_mutex_lock(&b3e_call);
  pthread_mutex_lock(&b3e_mu);
  j.done = 0;
  j.copied = 0;
  b3e_job = &j;
  pthread_cond_signal(&b3e_posted);
  while (j.done == 0 && b3e_state == 1) {
    pthread_cond_wait(&b3e_finished, &b3e_mu);
  }
  pthread_mutex_unlock(&b3e_mu);
  pthread_mutex_unlock(&b3e_call);
  return j.done == 1;
}
