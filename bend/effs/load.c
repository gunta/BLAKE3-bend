// B3IO.load
// =========
//
// Reads every file of a list into Array<U32> blocks and answers them as a
// Files tree, balanced by bytes, in list order. This is the I/O half of
// b3sum: the hashing is Bend. A block holds bytes as little-endian words,
// zero-padded to the end of its last 64-byte block, which is what
// blake3.bend expects.
//
// A file of up to 1 GiB is one block (FFile). A larger one is cut into
// 1 GiB parts (FSegs): 2^20 chunks each, so every part but the last is a
// complete subtree of the file's BLAKE3 tree, and the Segs tree has the
// left-full shape of BLAKE3's own top levels. Files up to 4 TiB (2^32
// chunk counters) work this way.
//
// One pass of pthreads opens, stats, allocates and reads each file. A
// thread allocates from an ALC row of its own past the pool's (rows
// pool_size..CUBE_T are never used on the CPU), so the per-thread heap
// allocator is safe here; the pool itself is parked while an effect runs.
// A part of 1 MiB or more is mapped over a page-aligned block instead of
// read (CPU heap only: a GPU heap is a Metal buffer). On a GPU heap a large
// part is read in 4 MiB slices by every thread.

#include <sys/stat.h>

#define B3_SLICE   (4ull << 20)

static u64* b3_heap;
#define B3_MAP_MIN (1ull << 20)
#define B3_SEG     (1ull << 30)
#define B3_MAX     (1ull << 42)

typedef struct {
  u64   off;
  u64   len;
  u64   loc;
  u32   cls;
  bool  mapped;
  bool  late;
  void* kept;  // the daemon's reused block (B3Keep), if any
} B3Part;

typedef struct {
  char*   path;
  u64     plen;
  u32     slot;  // 1 + its index among B3IO.keep's paths, or 0
  bool    stream;  // not in the page cache: hashed segment by segment
  Term    name;
  int     fd;
  int     err;
  u64     len;
  u32     nparts;
  B3Part* parts;
  B3Part  one;
} B3File;

typedef struct {
  u32 file;
  u32 part;
  u64 off;
  u64 len;
} B3Slice;

typedef struct {
  B3File*  files;
  u32      nfiles;
  B3Slice* slices;
  u32      nslices;
  u32      next;
  u32      rows;
  u64*     heap;
  // a progressive load (B3IO.again_start): the part of each file, and how
  // many files of each part are still loading; NULL otherwise
  u32*            part;
  u32*            left;
  pthread_mutex_t mu;
  pthread_cond_t  cv;
} B3Jobs;

typedef struct {
  B3Jobs* j;
  u32     row;
} B3Arg;

static u64 b3_us(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (u64)t.tv_sec * 1000000ull + (u64)t.tv_nsec / 1000ull;
}

// When the process started, for B3IO_TRACE's timeline.
static u64 b3_t_start;

static void __attribute__((constructor)) b3_t_init(void) {
  b3_t_start = b3_us();
}

// 2^cls words hold the part's whole blocks: at least one block.
static u32 b3_cls(u64 len) {
  u64 words = ((len + 63) / 64) * 16;
  u32 c = 4;
  while ((1ull << c) < words) {
    c += 1;
  }
  return c;
}

static void b3_pread(int fd, char* dst, u64 off, u64 len) {
  u64 got = 0;
  while (got < len) {
    ssize_t n = pread(fd, dst + got, len - got, (off_t)(off + got));
    if (n <= 0) {
      if (n < 0 && errno == EINTR) {
        continue;
      }
      // a file that shrank reads as zeros past its end
      memset(dst + got, 0, len - got);
      return;
    }
    got += (u64)n;
  }
}

// Mapped files live in a zone of their own, 6 TB past the heap's start:
// still inside the 2^40 words a Term's loc can name, far past where the
// heap grows. A map into an empty hole is cheap; a MAP_FIXED over the
// heap's one big reservation splits it, under the VM map's lock, per file
// (1000 maps of 1 MiB: ~20 ms). Files take consecutive ranges, so a daemon
// releases a whole round with one munmap. The zone is only hinted, never
// forced: if the kernel puts the map elsewhere, the file is read instead.
#define B3_ZONE (6ull << 40)
#define B3_ZONE_MAX (1ull << 40)

static u64 b3_zone_used;

// Maps a part read-only and shared, as b3sum's memmap does: no read, no
// copy, no copy-on-write set-up (a 1 GiB private map costs 5 ms, a shared
// one nothing). The bytes past the file's end in its last VM page read as
// zero. The array is never freed (b3_arr keeps a reference), since a free
// writes a link into the block's first word and the zone is not heap.
static bool b3_map(u64* H, int fd, B3Part* p) {
  static u64 min;
  if (min == 0) {
    const char* m = getenv("B3IO_MAP_MIN");
    min = m != NULL ? strtoull(m, NULL, 10) : B3_MAP_MIN;
  }
  if (io_gpu || p->len < min) {
    return false;
  }
  u64 pg = (u64)getpagesize();
  u64 span = (p->len + pg - 1) & ~(pg - 1);
  u64 off = __atomic_fetch_add(&b3_zone_used, span, __ATOMIC_RELAXED);
  if (off + span > B3_ZONE_MAX) {
    return false;
  }
  char* want = (char*)H + B3_ZONE + off;
  void* at = mmap(want, span, PROT_READ, MAP_SHARED, fd, (off_t)p->off);
  if (at == MAP_FAILED) {
    return false;
  }
  if (at != want) {
    munmap(at, span);
    return false;
  }
  p->loc = (u64)(want - (char*)H) / 8;
  p->mapped = true;
  return true;
}

// A daemon on a GPU heap keeps one block per (kept path, part) across
// rounds and reads each round's bytes into it: the pages are already there,
// so a parallel pread runs at ~40 GB/s instead of faulting fresh heap pages
// in. Each block holds one reference of the loader's, so Bend never frees
// it; each round's array is that term with one more.
#define B3_PARTS_MAX 4096

typedef struct {
  Term arr;
  u64  loc;
  u32  cls;
} B3Keep;

static B3Keep* b3_reuse;   // [slot][part]
static u32     b3_reuse_slots;

static B3Keep* b3_reuse_at(u32 slot, u32 part) {
  if (slot == 0 || slot > b3_reuse_slots || part >= B3_PARTS_MAX) {
    return NULL;
  }
  return &b3_reuse[(u64)(slot - 1) * B3_PARTS_MAX + part];
}

// Maps, reads, or (a large part on a GPU heap) allocates the part for the
// slice pass.
static int b3_part(Env e, int fd, B3Part* p, B3Keep* keep) {
  p->cls = b3_cls(p->len);
  if (keep == NULL && b3_map(e.mem, fd, p)) {
    return 0;
  }
  if (keep != NULL && keep->arr != 0 && keep->cls == p->cls) {
    p->loc = keep->loc;
  } else {
    p->loc = heap_alloc(e, blk_wcls(0, p->cls));
    if (err_peek(e.mem)) {
      return ENOMEM;
    }
    if (keep != NULL) {
      *keep = (B3Keep){ term_keep(e, term_blk(0, p->cls, p->loc), 0), p->loc, p->cls };
    }
  }
  char* dst = (char*)(e.mem + p->loc);
  u64 padded = p->len == 0 ? 64 : ((p->len + 63) / 64) * 64;
  memset(dst + p->len, 0, padded - p->len);
  if (p->len > B3_SLICE) {
    p->late = true;
  } else {
    b3_pread(fd, dst, p->off, p->len);
  }
  return 0;
}

// "-" is standard input, read to its end and copied into parts (no
// mapping: a pipe has no pages to map, and a terminal no size).
static void b3_stdin(Env e, B3File* f) {
  u64 cap = 1 << 20, n = 0;
  char* buf = io_mem(malloc(cap));
  for (;;) {
    if (n == cap) {
      cap *= 2;
      buf = io_mem(realloc(buf, cap));
    }
    // macOS refuses a read of more than INT_MAX bytes
    u64 want = cap - n < B3_SEG ? cap - n : B3_SEG;
    ssize_t r = read(0, buf + n, want);
    if (r < 0 && errno == EINTR) {
      continue;
    }
    if (r <= 0) {
      if (r < 0) {
        f->err = errno;
      }
      break;
    }
    n += (u64)r;
  }
  if (!f->err && n >= B3_MAX) {
    f->err = EFBIG;
  }
  if (!f->err) {
    f->len = n;
    f->nparts = n <= B3_SEG ? 1 : (u32)((n + B3_SEG - 1) / B3_SEG);
    f->parts = f->nparts == 1 ? &f->one
      : io_mem(calloc(f->nparts, sizeof(B3Part)));
    for (u32 i = 0; i < f->nparts && !f->err; i += 1) {
      B3Part* p = &f->parts[i];
      p->off = (u64)i * B3_SEG;
      p->len = n - p->off < B3_SEG ? n - p->off : B3_SEG;
      p->cls = b3_cls(p->len);
      p->loc = heap_alloc(e, blk_wcls(0, p->cls));
      if (err_peek(e.mem)) {
        f->err = ENOMEM;
        break;
      }
      char* dst = (char*)(e.mem + p->loc);
      u64 padded = p->len == 0 ? 64 : ((p->len + 63) / 64) * 64;
      memcpy(dst, buf + p->off, p->len);
      memset(dst + p->len, 0, padded - p->len);
    }
  }
  free(buf);
}

// Streaming
// ---------
// A big file that is mostly not in the page cache streams instead of
// mapping: page faults on a mapping read the SSD in 16 KiB pieces (b3sum
// gets 0.75 GB/s that way here), while 16 threads of 8 MiB F_NOCACHE preads
// read it at 10-14 GB/s. B3IO.seg(id, k) hands Bend segment k (1 GiB, a
// complete subtree but the last) in one of two reused heap blocks, and
// starts reading k + 1 into the other before it returns, so the SSD and the
// hashing run at once.

#define B3_STREAM_MIN (256ull << 20)
#define B3_READERS 16
#define B3_RBLK (8ull << 20)

#ifndef MINCORE_INCORE
#define MINCORE_INCORE 1  // Linux: bit 0 of each mincore byte
#endif

// The fraction of the file's pages in the page cache, from 4096 samples.
static double b3_resident(int fd, u64 len) {
  u64 pg = (u64)getpagesize();
  char* at = mmap(NULL, len, PROT_READ, MAP_SHARED, fd, 0);
  if (at == MAP_FAILED) {
    return 1.0;
  }
  u64 pages = (len + pg - 1) / pg, hit = 0, n = pages < 4096 ? pages : 4096;
  for (u64 i = 0; i < n; i += 1) {
    unsigned char v = 0;
    u64 page = i * pages / n;
    if (mincore(at + page * pg, pg, (void*)&v) == 0 && (v & MINCORE_INCORE)) {
      hit += 1;
    }
  }
  munmap(at, len);
  return (double)hit / (double)n;
}

// Whether to stream a big file: when under 90% of it is cached.
// B3IO_STREAM=always or =never overrides it, for tests.
static bool b3_stream_pick(int fd, u64 len) {
  const char* force = getenv("B3IO_STREAM");
  if (force != NULL && strcmp(force, "always") == 0) {
    return true;
  }
  if (force != NULL && strcmp(force, "never") == 0) {
    return false;
  }
  return b3_resident(fd, len) < 0.9;
}

typedef struct {
  int       fd;
  u64       len;
  u32       nseg;
  Term      arr[2];   // the two reused blocks (loader's references), 0 = none
  u64       loc[2];
  pthread_t reader;   // the read of `ahead` into block ahead % 2, if running
  bool      busy;
  u32       ahead;
  // the running read
  char*     dst;
  u64       off;
  u64       left;
  u64       next;
} B3Stream;

static B3Stream* b3_streams;
static u32       b3_nstreams, b3_scap;

static void* b3_read_slice(void* arg) {
  B3Stream* st = arg;
  for (;;) {
    u64 i = __atomic_fetch_add(&st->next, B3_RBLK, __ATOMIC_RELAXED);
    if (i >= st->left) {
      return NULL;
    }
    u64 n = st->left - i < B3_RBLK ? st->left - i : B3_RBLK;
    b3_pread(st->fd, st->dst + i, st->off + i, n);
  }
}

// Reads [off, off + len) into dst on B3_READERS threads, and waits.
static void* b3_read_all(void* arg) {
  B3Stream* st = arg;
  pthread_t tid[B3_READERS];
  u32 n = 1;
  st->next = 0;
  for (; n < B3_READERS; n += 1) {
    if (pthread_create(&tid[n], NULL, b3_read_slice, st) != 0) {
      break;
    }
  }
  b3_read_slice(st);
  for (u32 t = 1; t < n; t += 1) {
    pthread_join(tid[t], NULL);
  }
  return NULL;
}

static void b3_seg_geom(B3Stream* st, u32 k, u64* off, u64* len) {
  *off = (u64)k * B3_SEG;
  *len = st->len - *off < B3_SEG ? st->len - *off : B3_SEG;
}

static void b3_seg_start(B3Stream* st, u32 k) {
  u64 off, len;
  b3_seg_geom(st, k, &off, &len);
  st->dst = (char*)(b3_heap + st->loc[k % 2]);
  st->off = off;
  st->left = len;
  st->ahead = k;
  st->busy = pthread_create(&st->reader, NULL, b3_read_all, st) == 0;
  if (!st->busy) {
    b3_read_all(st);
  }
}

static void b3_file(Env e, B3File* f) {
  struct stat st;
  if (f->plen == 1 && f->path[0] == '-') {
    b3_stdin(e, f);
    return;
  }
  f->fd = open(f->path, O_RDONLY);
  if (f->fd < 0) {
    f->err = errno;
    return;
  }
  bool late = false;
  if (fstat(f->fd, &st) != 0) {
    f->err = errno;
  } else if (S_ISDIR(st.st_mode)) {
    f->err = EISDIR;
  } else if ((u64)st.st_size >= B3_MAX) {
    f->err = EFBIG;
  } else if (!io_gpu && f->slot == 0 && (u64)st.st_size >= B3_STREAM_MIN
      && b3_stream_pick(f->fd, (u64)st.st_size)) {
    // mostly on disk: B3IO.seg streams it (fd stays open)
    f->len = (u64)st.st_size;
    f->stream = true;
    return;
  } else {
    f->len = (u64)st.st_size;
    f->nparts = f->len <= B3_SEG ? 1 : (u32)((f->len + B3_SEG - 1) / B3_SEG);
    f->parts = f->nparts == 1 ? &f->one
      : io_mem(calloc(f->nparts, sizeof(B3Part)));
    for (u32 i = 0; i < f->nparts && !f->err; i += 1) {
      B3Part* p = &f->parts[i];
      p->off = (u64)i * B3_SEG;
      p->len = f->len - p->off < B3_SEG ? f->len - p->off : B3_SEG;
      B3Keep* keep = io_gpu ? b3_reuse_at(f->slot, i) : NULL;
      f->err = b3_part(e, f->fd, p, keep);
      p->kept = keep;
      late |= p->late;
    }
  }
  if (!late || f->err) {
    close(f->fd);
    f->fd = -1;
  }
}

static void* b3_file_job(void* arg) {
  B3Arg*  a = arg;
  B3Jobs* j = a->j;
  Env     e = { j->heap, ALC[a->row] };
  for (;;) {
    u32 i = __atomic_fetch_add(&j->next, 1, __ATOMIC_RELAXED);
    if (i >= j->nfiles) {
      return NULL;
    }
    b3_file(e, &j->files[i]);
    if (j->left != NULL && __atomic_sub_fetch(&j->left[j->part[i]], 1, __ATOMIC_ACQ_REL) == 0) {
      pthread_mutex_lock(&j->mu);
      pthread_cond_broadcast(&j->cv);
      pthread_mutex_unlock(&j->mu);
    }
  }
}

static void* b3_slice_job(void* arg) {
  B3Jobs* j = ((B3Arg*)arg)->j;
  for (;;) {
    u32 i = __atomic_fetch_add(&j->next, 1, __ATOMIC_RELAXED);
    if (i >= j->nslices) {
      return NULL;
    }
    B3Slice* s = &j->slices[i];
    B3File*  f = &j->files[s->file];
    B3Part*  p = &f->parts[s->part];
    b3_pread(f->fd, (char*)(j->heap + p->loc) + (s->off - p->off), s->off, s->len);
  }
}

// Runs job on n threads, each with its own spare ALC row.
static void b3_pool(B3Jobs* j, void* (*job)(void*), u32 n) {
  pthread_t tid[CUBE_T];
  B3Arg     arg[CUBE_T];
  n = n < 1 ? 1 : n > j->rows ? j->rows : n;
  j->next = 0;
  for (u32 t = 0; t < n; t += 1) {
    arg[t] = (B3Arg){ j, pool_size + t };
  }
  for (u32 t = 1; t < n; t += 1) {
    if (pthread_create(&tid[t], NULL, job, &arg[t]) != 0) {
      n = t;
      break;
    }
  }
  job(&arg[0]);
  for (u32 t = 1; t < n; t += 1) {
    pthread_join(tid[t], NULL);
  }
}

// A String's UTF-8, read in place: the String stays, as the file's name.
static char* b3_cstr(Env e, Term s, u64* len) {
  u64   cap = 64, n = 0;
  char* buf = io_mem(malloc(cap));
  while (term_aux(s) == CID_SCon) {
    u64 at = term_peek(e.mem, s);
    if (n + 5 > cap) {
      cap *= 2;
      buf = io_mem(realloc(buf, cap));
    }
    n += io_utf8(buf + n, e.mem[at]);
    s = e.mem[at + 1];
  }
  buf[n] = 0;
  *len = n;
  return buf;
}

static Term b3_ctr(Env e, u64 cid, u32 n, Term* v) {
  u64 l = heap_alloc(e, cls_fit(n));
  for (u32 i = 0; i < n; i += 1) {
    e.mem[l + i] = io_seal(e, v[i], cid);
  }
  return term_ctr(cid, l);
}

// The mapped blocks handed out, each with the reference the loader keeps
// so that Bend never frees (writes to) a read-only page. B3IO.release puts
// zero pages back over them and drops that reference, as a daemon must.
typedef struct {
  Term  arr;
  char* at;
  u64   span;
} B3Kept;

static B3Kept* b3_kept;
static u32     b3_nkept, b3_kcap;

static Term b3_arr(Env e, B3Part* p) {
  if (p->kept != NULL) {
    // the reused block's own term, one reference more for this round
    return term_keep(e, ((B3Keep*)p->kept)->arr, 1);
  }
  Term arr = term_blk(0, p->cls, p->loc);
  if (!p->mapped) {
    return arr;
  }
  arr = term_keep(e, arr, 1);
  if (b3_nkept == b3_kcap) {
    b3_kcap = b3_kcap ? b3_kcap * 2 : 64;
    b3_kept = io_mem(realloc(b3_kept, b3_kcap * sizeof(B3Kept)));
  }
  u64 pg = (u64)getpagesize();
  b3_kept[b3_nkept++] = (B3Kept){ arr, (char*)(e.mem + p->loc),
    (p->len + pg - 1) & ~(pg - 1) };
  return arr;
}

// Parts lo..hi-1 as BLAKE3's left-full tree: the left side takes the
// largest power of two of parts below the count.
static Term b3_segs(Env e, B3File* f, u32 lo, u32 hi) {
  if (hi - lo == 1) {
    B3Part* p = &f->parts[lo];
    u64 nch = (p->len + 1023) / 1024;
    Term v[4] = { b3_arr(e, p), (Term)(u32)(p->off >> 10), (Term)(u32)nch,
      (Term)(u32)(p->len - (nch - 1) * 1024) };
    return b3_ctr(e, CID(SLeaf), 4, v);
  }
  u32 left = 1;
  while (left * 2 < hi - lo) {
    left *= 2;
  }
  Term v[2] = { b3_segs(e, f, lo, lo + left), b3_segs(e, f, lo + left, hi) };
  return b3_ctr(e, CID(SNode), 2, v);
}

static Term b3_leaf(Env e, B3File* f) {
  if (f->stream && !f->err) {
    if (b3_nstreams == b3_scap) {
      b3_scap = b3_scap ? b3_scap * 2 : 8;
      b3_streams = io_mem(realloc(b3_streams, b3_scap * sizeof(B3Stream)));
    }
    u32 id = b3_nstreams++;
    B3Stream* st = &b3_streams[id];
    memset(st, 0, sizeof(B3Stream));
    st->fd = f->fd;
    st->len = f->len;
    st->nseg = (u32)((f->len + B3_SEG - 1) / B3_SEG);
#ifdef F_NOCACHE
    fcntl(st->fd, F_NOCACHE, 1);
#else
    posix_fadvise(st->fd, 0, 0, POSIX_FADV_SEQUENTIAL);
#endif
    f->fd = -1;
    Term v[3] = { (Term)id, (Term)st->nseg, f->name };
    return b3_ctr(e, CID(FStream), 3, v);
  }
  if (f->err) {
    const char* msg = strerror(f->err);
    return io_node(e, CID(FErr), io_str(e, msg, strlen(msg)), f->name);
  }
  if (f->nparts > 1) {
    return io_node(e, CID(FSegs), b3_segs(e, f, 0, f->nparts), f->name);
  }
  Term v[3] = { b3_arr(e, &f->parts[0]), (Term)(u32)f->len, f->name };
  return b3_ctr(e, CID(FFile), 3, v);
}

// Files lo..hi-1 as a tree whose halves hold about the same bytes.
static Term b3_tree(Env e, B3File* fs, u64* pre, u32 lo, u32 hi) {
  if (hi - lo == 1) {
    return b3_leaf(e, &fs[lo]);
  }
  u64 half = pre[lo] + (pre[hi] - pre[lo]) / 2;
  u32 a = lo + 1, b = hi - 1;
  while (a < b) {
    u32 m = (a + b) / 2;
    if (pre[m] < half) {
      a = m + 1;
    } else {
      b = m;
    }
  }
  Term l = b3_tree(e, fs, pre, lo, a);
  Term r = b3_tree(e, fs, pre, a, hi);
  return io_node(e, CID(FPair), l, r);
}

// B3IO_TRACE=1 prints each phase's microseconds to stderr.
#define B3_MARK(name) if (trace) { u64 t1 = b3_us(); \
  fprintf(stderr, "b3io %-6s %8llu us\n", name, (unsigned long long)(t1 - t0)); \
  t0 = t1; }

static Term b3_load(Env e, B3File* fs, u32 n, u32 threads, bool trace, u64 t0);

Term b3io_load_run(Env e, Term* f, IoWork* w) {
  bool trace = getenv("B3IO_TRACE") != NULL;
  u64  t0 = b3_us();
  if (trace) {
    fprintf(stderr, "b3io start  %8llu us after exec\n",
      (unsigned long long)(t0 - b3_t_start));
  }
  u32  threads = (u32)f[1];
  u32  cap = 64, n = 0;
  b3_heap = e.mem;
  B3File* fs = io_mem(malloc(cap * sizeof(B3File)));
  Term xs = f[0];
  while (term_aux(xs) == CID_Con) {
    Term fb[2];
    spare_free(e, cls_fit(2), ctr_take(e, xs, 2, fb));
    if (n == cap) {
      cap *= 2;
      fs = io_mem(realloc(fs, cap * sizeof(B3File)));
    }
    memset(&fs[n], 0, sizeof(B3File));
    fs[n].name = fb[0];
    fs[n].path = b3_cstr(e, fb[0], &fs[n].plen);
    fs[n].fd = -1;
    n += 1;
    xs = fb[1];
  }
  B3_MARK("args")
  return b3_load(e, fs, n, threads, trace, t0);
}

// Loads files fs[0..n-1] (paths and names set), frees fs, answers Files.
static Term b3_load(Env e, B3File* fs, u32 n, u32 threads, bool trace, u64 t0) {
  if (n == 0) {
    free(fs);
    return term_pak(CID(FNone), 0);
  }
  B3Jobs j = { .files = fs, .nfiles = n, .heap = e.mem,
    .rows = CUBE_T + 1 - pool_size };
  b3_pool(&j, b3_file_job, n < threads ? n : threads);
  B3_MARK("files")

  // large parts on a GPU heap: every thread reads a slice
  u32 ns = 0, scap = 16;
  B3Slice* ss = io_mem(malloc(scap * sizeof(B3Slice)));
  for (u32 i = 0; i < n; i += 1) {
    for (u32 k = 0; !fs[i].err && k < fs[i].nparts; k += 1) {
      B3Part* p = &fs[i].parts[k];
      for (u64 off = 0; p->late && off < p->len; off += B3_SLICE) {
        if (ns == scap) {
          scap *= 2;
          ss = io_mem(realloc(ss, scap * sizeof(B3Slice)));
        }
        u64 left = p->len - off;
        ss[ns++] = (B3Slice){ i, k, p->off + off, left < B3_SLICE ? left : B3_SLICE };
      }
    }
  }
  if (ns > 0) {
    j.slices = ss;
    j.nslices = ns;
    b3_pool(&j, b3_slice_job, ns < threads ? ns : threads);
    B3_MARK("slices")
  }
  u64* pre = io_mem(malloc((n + 1) * sizeof(u64)));
  pre[0] = 0;
  for (u32 i = 0; i < n; i += 1) {
    if (fs[i].fd >= 0 && !fs[i].stream) {
      close(fs[i].fd);
      fs[i].fd = -1;
    }
    // a streamed file is hashed later, apart: it weighs nothing here
    pre[i + 1] = pre[i] + (fs[i].stream ? 0 : fs[i].len) + 64;
    free(fs[i].path);
  }
  Term t = b3_tree(e, fs, pre, 0, n);
  for (u32 i = 0; i < n; i += 1) {
    if (fs[i].parts != &fs[i].one) {
      free(fs[i].parts);
    }
  }
  free(fs);
  free(ss);
  free(pre);
  B3_MARK("tree")
  return t;
}

#ifdef CID(B3IO.seg)

// B3IO.seg(id, k): segment k of stream id, read by now; reading k + 1
// into the other block starts before this returns.
Term b3io_seg_run(Env e, Term* f, IoWork* w) {
  B3Stream* st = &b3_streams[(u32)f[0]];
  u32 k = (u32)f[1];
  u32 cls = b3_cls(B3_SEG);
  for (u32 b = 0; b < 2; b += 1) {
    if (st->arr[b] == 0) {
      st->loc[b] = heap_alloc(e, blk_wcls(0, cls));
      st->arr[b] = term_keep(e, term_blk(0, cls, st->loc[b]), 0);
    }
  }
  if (st->busy) {
    pthread_join(st->reader, NULL);
    st->busy = false;
  }
  if (st->ahead != k || st->left == 0) {
    u64 off, len;
    b3_seg_geom(st, k, &off, &len);
    st->dst = (char*)(e.mem + st->loc[k % 2]);
    st->off = off;
    st->left = len;
    st->ahead = k;
    b3_read_all(st);
  }
  u64 off, len;
  b3_seg_geom(st, k, &off, &len);
  char* dst = (char*)(e.mem + st->loc[k % 2]);
  u64 padded = len == 0 ? 64 : ((len + 63) / 64) * 64;
  memset(dst + len, 0, padded - len);
  if (k + 1 < st->nseg) {
    b3_seg_start(st, k + 1);
  } else {
    close(st->fd);
    st->fd = -1;
  }
  u64 nch = (len + 1023) / 1024;
  nch = nch ? nch : 1;
  Term v[4] = { term_keep(e, st->arr[k % 2], 1), (Term)(u32)(off >> 10),
    (Term)(u32)nch, (Term)(u32)(len - (nch - 1) * 1024) };
  return b3_ctr(e, CID(Part), 4, v);
}

#endif

// The daemon's side: keep a list of paths once, then load them again and
// again, with empty names, as a sync service re-hashes what it watches.

static char** b3_saved;
static u32    b3_nsaved;

Term b3io_keep_run(Env e, Term* f, IoWork* w) {
  for (u32 i = 0; i < b3_nsaved; i += 1) {
    free(b3_saved[i]);
  }
  b3_nsaved = 0;
  u32 cap = 64;
  b3_saved = io_mem(realloc(b3_saved, cap * sizeof(char*)));
  Term xs = f[0];
  while (term_aux(xs) == CID_Con) {
    Term fb[2];
    spare_free(e, cls_fit(2), ctr_take(e, xs, 2, fb));
    if (b3_nsaved == cap) {
      cap *= 2;
      b3_saved = io_mem(realloc(b3_saved, cap * sizeof(char*)));
    }
    u64 len;
    b3_saved[b3_nsaved++] = b3_cstr(e, fb[0], &len);
    term_sink(e, fb[0]);
    xs = fb[1];
  }
  return (Term)b3_nsaved;
}

Term b3io_again_run(Env e, Term* f, IoWork* w) {
  if (io_gpu && b3_reuse_slots != b3_nsaved) {
    free(b3_reuse);
    b3_reuse = io_mem(calloc((u64)(b3_nsaved ? b3_nsaved : 1) * B3_PARTS_MAX, sizeof(B3Keep)));
    b3_reuse_slots = b3_nsaved;
  }
  B3File* fs = io_mem(calloc(b3_nsaved ? b3_nsaved : 1, sizeof(B3File)));
  for (u32 i = 0; i < b3_nsaved; i += 1) {
    fs[i].slot = i + 1;
    fs[i].path = strdup(b3_saved[i]);
    fs[i].plen = strlen(fs[i].path);
    fs[i].name = term_pak(CID_SNil, 0);
    fs[i].fd = -1;
  }
  bool trace = getenv("B3IO_TRACE") != NULL;
  return b3_load(e, fs, b3_nsaved, (u32)f[0], trace, b3_us());
}

// Every mapped file of the round goes in one munmap of the zone's used
// range; the kept references are left as they are (a word each), since a
// zone block must not reach the heap's free lists.
// A progressive round: B3IO.again_start(threads) starts loading every kept
// path on background threads, in order, and returns how many parts it cut
// them into; B3IO.again_take(k) waits for part k alone and answers its
// Files. Bend hashes part k on every core while parts k + 1.. are still
// opening (on many small files, the open() calls are most of the round).

#define B3_PARTS 8

static struct {
  B3Jobs    j;
  pthread_t coord;
  u32       parts;
  u32       threads;
  bool      at_once;  // a GPU heap loads the round in one go, as part 0
  Term      whole;
} b3_prog;

static void* b3_prog_main(void* arg) {
  B3Jobs* j = arg;
  b3_pool(j, b3_file_job, j->nfiles < b3_prog.threads ? j->nfiles : b3_prog.threads);
  return NULL;
}

Term b3io_again_start_run(Env e, Term* f, IoWork* w) {
  u32 threads = (u32)f[0];
  u32 n = b3_nsaved;
  b3_heap = e.mem;
  if (io_gpu || n == 0) {
    // the slice pass for big parts on a GPU heap runs after every open:
    // load it all now, hand it out as part 0
    Term args[1] = { (Term)threads };
    b3_prog.whole = b3io_again_run(e, args, w);
    b3_prog.at_once = true;
    b3_prog.parts = 1;
    return (Term)1;
  }
  B3File* fs = io_mem(calloc(n, sizeof(B3File)));
  for (u32 i = 0; i < n; i += 1) {
    fs[i].path = strdup(b3_saved[i]);
    fs[i].plen = strlen(fs[i].path);
    fs[i].slot = i + 1;  // a daemon's file: mapped or read, never streamed
    fs[i].name = term_pak(CID_SNil, 0);
    fs[i].fd = -1;
  }
  const char* pe = getenv("B3IO_PARTS");
  u32 want = pe != NULL && atoi(pe) > 0 ? (u32)atoi(pe) : B3_PARTS;
  u32 parts = n < want ? n : want;
  B3Jobs* j = &b3_prog.j;
  memset(j, 0, sizeof(*j));
  j->files = fs;
  j->nfiles = n;
  j->heap = e.mem;
  j->rows = CUBE_T + 1 - pool_size;
  j->part = io_mem(malloc(n * sizeof(u32)));
  j->left = io_mem(calloc(parts, sizeof(u32)));
  for (u32 i = 0; i < n; i += 1) {
    j->part[i] = (u32)((u64)i * parts / n);
    j->left[j->part[i]] += 1;
  }
  pthread_mutex_init(&j->mu, NULL);
  pthread_cond_init(&j->cv, NULL);
  b3_prog.parts = parts;
  b3_prog.threads = threads;
  b3_prog.at_once = false;
  pthread_create(&b3_prog.coord, NULL, b3_prog_main, j);
  return (Term)parts;
}

Term b3io_again_take_run(Env e, Term* f, IoWork* w) {
  u32 k = (u32)f[0];
  if (b3_prog.at_once) {
    Term t = k == 0 ? b3_prog.whole : term_pak(CID(FNone), 0);
    b3_prog.whole = term_pak(CID(FNone), 0);
    return t;
  }
  B3Jobs* j = &b3_prog.j;
  B3File* fs = j->files;
  u32 n = j->nfiles, parts = b3_prog.parts;
  pthread_mutex_lock(&j->mu);
  while (__atomic_load_n(&j->left[k], __ATOMIC_ACQUIRE) != 0) {
    pthread_cond_wait(&j->cv, &j->mu);
  }
  pthread_mutex_unlock(&j->mu);
  u32 lo = 0;
  while (lo < n && j->part[lo] < k) {
    lo += 1;
  }
  u32 hi = lo;
  while (hi < n && j->part[hi] == k) {
    hi += 1;
  }
  u64* pre = io_mem(malloc((hi - lo + 1) * sizeof(u64)));
  pre[0] = 0;
  for (u32 i = lo; i < hi; i += 1) {
    if (fs[i].fd >= 0 && !fs[i].stream) {
      close(fs[i].fd);
      fs[i].fd = -1;
    }
    pre[i - lo + 1] = pre[i - lo] + fs[i].len + 64;
    free(fs[i].path);
  }
  Term t = hi > lo ? b3_tree(e, fs + lo, pre, 0, hi - lo) : term_pak(CID(FNone), 0);
  free(pre);
  if (k + 1 >= parts) {
    pthread_join(b3_prog.coord, NULL);
    for (u32 i = 0; i < n; i += 1) {
      if (fs[i].parts != &fs[i].one) {
        free(fs[i].parts);
      }
    }
    free(fs);
    free(j->part);
    free(j->left);
    pthread_mutex_destroy(&j->mu);
    pthread_cond_destroy(&j->cv);
    j->files = NULL;
  }
  return t;
}

Term b3io_release_run(Env e, Term* f, IoWork* w) {
  u64 t0 = b3_us();
  u32 kept = b3_nkept;
  if (b3_zone_used > 0) {
    munmap((char*)e.mem + B3_ZONE, b3_zone_used);
    b3_zone_used = 0;
  }
  b3_nkept = 0;
  if (getenv("B3IO_TRACE") != NULL) {
    fprintf(stderr, "b3io release %u maps %llu us\n", kept,
      (unsigned long long)(b3_us() - t0));
  }
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) b3io_load_use(void) {
#ifdef CID(B3IO.load)
  io_eff(CID(B3IO.load), b3io_load_run);
#endif
#ifdef CID(B3IO.seg)
  io_eff(CID(B3IO.seg), b3io_seg_run);
#endif
#ifdef CID(B3IO.keep)
  io_eff(CID(B3IO.keep), b3io_keep_run);
#endif
#ifdef CID(B3IO.again)
  io_eff(CID(B3IO.again), b3io_again_run);
#endif
#ifdef CID(B3IO.release)
  io_eff(CID(B3IO.release), b3io_release_run);
#endif
#ifdef CID(B3IO.again_start)
  io_eff(CID(B3IO.again_start), b3io_again_start_run);
#endif
#ifdef CID(B3IO.again_take)
  io_eff(CID(B3IO.again_take), b3io_again_take_run);
#endif
}
