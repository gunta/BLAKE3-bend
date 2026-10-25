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
#define B3_MAP_MIN (1ull << 20)
#define B3_SEG     (1ull << 30)
#define B3_MAX     (1ull << 42)

typedef struct {
  u64  off;
  u64  len;
  u64  loc;
  u32  cls;
  bool mapped;
  bool late;
} B3Part;

typedef struct {
  char*   path;
  u64     plen;
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

// A fresh block of class cls whose first byte sits on a VM page, so a file
// can be mapped over it: the heap's bump pointer moves past up to 15 KiB.
static u64 b3_page_block(u64* H, u32 cls) {
  u32 pages = (1u << cls) >> PAGE_BITS;
  u32 vm = (u32)(getpagesize() / (PAGE_LEN * 8));
  vm = vm < 1 ? 1 : vm;
  u32 p0 = a32_add(a32_at(H, H_BUMP), pages + vm - 1);
  u64 need = (u64)p0 + pages + vm - 1;
  if (need > a32_load_acq(a32_at(H, H_CAP)) && !corpus_grow(H, need)) {
    return 0;
  }
  for (u32 p = p0; p < p0 + vm; p += 1) {
    u64 loc = HEAP_OFF + ((u64)p << PAGE_BITS);
    if (((uintptr_t)(H + loc) & (uintptr_t)(getpagesize() - 1)) == 0) {
      return loc;
    }
  }
  return 0;
}

// Maps a part over its block, read-only and shared, as b3sum's memmap
// does: no read, no copy, and no copy-on-write setup (a 1 GiB private map
// costs 5 ms, a shared one nothing). The bytes past the part's last VM page
// are the heap's own zero pages. A freed block takes a free-list link in
// its first word, so a mapped block is never freed: b3_arr keeps one
// reference to it for the life of the process.
static bool b3_map(u64* H, int fd, B3Part* p) {
  if (io_gpu || p->len < B3_MAP_MIN || p->cls < PAGE_BITS + 2) {
    return false;
  }
  u64 loc = b3_page_block(H, blk_wcls(0, p->cls));
  if (loc == 0) {
    return false;
  }
  u64 pg = (u64)getpagesize();
  u64 span = (p->len + pg - 1) & ~(pg - 1);
  void* at = mmap((char*)(H + loc), span, PROT_READ, MAP_SHARED | MAP_FIXED, fd,
    (off_t)p->off);
  if (at == MAP_FAILED) {
    return false;
  }
  p->loc = loc;
  p->mapped = true;
  return true;
}

// Maps, reads, or (a large part on a GPU heap) allocates the part for the
// slice pass.
static int b3_part(Env e, int fd, B3Part* p) {
  p->cls = b3_cls(p->len);
  if (b3_map(e.mem, fd, p)) {
    return 0;
  }
  p->loc = heap_alloc(e, blk_wcls(0, p->cls));
  if (err_peek(e.mem)) {
    return ENOMEM;
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
  } else {
    f->len = (u64)st.st_size;
    f->nparts = f->len <= B3_SEG ? 1 : (u32)((f->len + B3_SEG - 1) / B3_SEG);
    f->parts = f->nparts == 1 ? &f->one
      : io_mem(calloc(f->nparts, sizeof(B3Part)));
    for (u32 i = 0; i < f->nparts && !f->err; i += 1) {
      B3Part* p = &f->parts[i];
      p->off = (u64)i * B3_SEG;
      p->len = f->len - p->off < B3_SEG ? f->len - p->off : B3_SEG;
      f->err = b3_part(e, f->fd, p);
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

static Term b3_arr(Env e, B3Part* p) {
  Term arr = term_blk(0, p->cls, p->loc);
  return p->mapped ? term_keep(e, arr, 1) : arr;
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

Term b3io_load_run(Env e, Term* f, IoWork* w) {
  bool trace = getenv("B3IO_TRACE") != NULL;
  u64  t0 = b3_us();
  if (trace) {
    fprintf(stderr, "b3io start  %8llu us after exec\n",
      (unsigned long long)(t0 - b3_t_start));
  }
  u32  threads = (u32)f[1];
  u32  cap = 64, n = 0;
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
  if (n == 0) {
    free(fs);
    return term_pak(CID(FNone), 0);
  }
  B3_MARK("args")
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
    if (fs[i].fd >= 0) {
      close(fs[i].fd);
    }
    pre[i + 1] = pre[i] + fs[i].len + 64;
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

static void __attribute__((constructor)) b3io_load_use(void) {
  io_eff(CID(B3IO.load), b3io_load_run);
}
