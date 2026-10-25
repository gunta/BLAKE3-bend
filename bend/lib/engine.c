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

#include <pthread.h>

#define B3E_SPANS 64  // spans a job, read in place
#define B3E_STAGE 2   // spans a job, copied

typedef struct B3EJob {
  const unsigned char* p[B3E_SPANS];
  u64 len[B3E_SPANS];  // bytes, at most 1 GiB
  u64 cb[B3E_SPANS];   // chunk counter of the first chunk
  u32 n;
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

// What Eng.next lent Bend for the current job: zero-copy redirect cells to
// release once its CVs are out.
static Term b3e_lent[B3E_SPANS];
static u32  b3e_nlent;

// BLAKE3_BEND_TRACE=1 prints these at exit.
static u64 b3e_njobs, b3e_nspans, b3e_ncopied, b3e_bytes, b3e_cbytes, b3e_copy_ns,
  b3e_wait_ns, b3e_hash_ns, b3e_t_next;

static u64 b3e_ns(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (u64)t.tv_sec * 1000000000ull + (u64)t.tv_nsec;
}

static void b3e_report(void) {
  fprintf(stderr, "blake3-bend: %llu jobs, %llu spans (%llu copied), %llu bytes (%llu copied);"
    " copying %.3f ms (%.3f ms of it waited for), hashing %.3f ms\n",
    (unsigned long long)b3e_njobs, (unsigned long long)b3e_nspans,
    (unsigned long long)b3e_ncopied, (unsigned long long)b3e_bytes,
    (unsigned long long)b3e_cbytes, b3e_copy_ns / 1e6, b3e_wait_ns / 1e6, b3e_hash_ns / 1e6);
}

// Bend can read len bytes at p in place: word-aligned, inside the window
// past the heap's base, and ending on a 64-byte block (Bend reads whole
// blocks, and a short last block's tail must be zeros).
int b3e_inside(const void* p, uint64_t len) {
  uintptr_t base = (uintptr_t)b3e_heap, at = (uintptr_t)p;
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
    u64 len = j->len[lo], nch = (len + 1023) / 1024;
    Term v[4] = { b3e_arr(e, j, lo, k), (Term)(u32)j->cb[lo], (Term)(u32)nch,
      (Term)(u32)(len - (nch - 1) * 1024) };
    return b3e_ctr(e, CID(SpOne), 4, v);
  }
  u32 mid = lo + (hi - lo) / 2;
  Term l = b3e_spans(e, j, lo, mid, k);
  Term r = b3e_spans(e, j, mid, hi, k);
  Term v[2] = { l, r };
  return b3e_ctr(e, CID(SpTwo), 2, v);
}

// Eng.next: the next job's spans, once a caller posts one; the copy of the
// job after it starts before Bend sees these.
Term eng_next_run(Env e, Term* f, IoWork* w) {
  static int set;
  pthread_mutex_lock(&b3e_mu);
  b3e_heap = e.mem;
  pthread_cond_broadcast(&b3e_finished);  // b3e_start waits for the first
  while (b3e_head == NULL) {
    pthread_cond_wait(&b3e_posted, &b3e_mu);
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

static pthread_once_t b3e_once = PTHREAD_ONCE_INIT;

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

// Hashes n spans (each at most 1 GiB) into out[0..n-1]: B3E_SPANS a job
// while they can be read in place, B3E_STAGE copied ones a job, every job
// queued at once. 1 on success, 0 if the engine is not running (the caller
// then hashes in C).
int b3e_hash(uint32_t n, const unsigned char* const* p, const uint64_t* len,
             const uint64_t* cb, unsigned char (*out)[32]) {
  if (n == 0 || !b3e_start()) {
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
