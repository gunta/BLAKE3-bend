// B3IO.emit
// =========
//
// Writes b3sum's output for an Out tree, in tree order: "<hex>  <name>"
// for each hash on stdout, "b3sum: <name>: <message>" for each error on
// stderr, each in one write. It answers the number of errors. The hex is
// the CV's eight words as little-endian bytes, as BLAKE3 defines the
// output; no hashing happens here.

typedef struct {
  char* p;
  u64   n;
  u64   cap;
} B3Buf;

static void b3_room(B3Buf* b, u64 more) {
  if (b->n + more > b->cap) {
    while (b->n + more > b->cap) {
      b->cap = b->cap ? b->cap * 2 : 1 << 16;
    }
    b->p = io_mem(realloc(b->p, b->cap));
  }
}

static void b3_put(B3Buf* b, const char* s, u64 n) {
  b3_room(b, n);
  memcpy(b->p + b->n, s, n);
  b->n += n;
}

static void b3_put_str(Env e, B3Buf* b, Term s) {
  while (term_aux(s) == CID_SCon) {
    u64 at = term_peek(e.mem, s);
    b3_room(b, 4);
    b->n += io_utf8(b->p + b->n, e.mem[at]);
    s = e.mem[at + 1];
  }
}

// The eight words at e.mem[at..at+7].
static void b3_put_hex(Env e, B3Buf* b, u64 at) {
  static const char dig[] = "0123456789abcdef";
  b3_room(b, 64);
  for (u32 i = 0; i < 8; i += 1) {
    u32 x = (u32)e.mem[at + i];
    for (u32 k = 0; k < 4; k += 1) {
      u32 byte = (x >> (8 * k)) & 0xFF;
      b->p[b->n++] = dig[byte >> 4];
      b->p[b->n++] = dig[byte & 15];
    }
  }
}

#ifdef CID(B3IO.emit)

static void b3_emit(Env e, Term o, B3Buf* out, B3Buf* err, u32* nerr) {
  u64 cid = term_aux(o);
  if (cid == CID(OPair)) {
    u64 at = term_peek(e.mem, o);
    b3_emit(e, e.mem[at], out, err, nerr);
    b3_emit(e, e.mem[at + 1], out, err, nerr);
  } else if (cid == CID(OHash)) {
    // bend flattens the CV record into OHash: eight words, then the name;
    // a boxed CV (arity 2) is a pointer to its eight words
    u64 at = term_peek(e.mem, o);
    bool flat = cid_arity(CID(OHash)) == 9;
    b3_put_hex(e, out, flat ? at : term_peek(e.mem, e.mem[at]));
    b3_put(out, "  ", 2);
    b3_put_str(e, out, e.mem[at + (flat ? 8 : 1)]);
    b3_put(out, "\n", 1);
  } else if (cid == CID(OErr)) {
    u64 at = term_peek(e.mem, o);
    b3_put(err, "b3sum: ", 7);
    b3_put_str(e, err, e.mem[at + 1]);
    b3_put(err, ": ", 2);
    b3_put_str(e, err, e.mem[at]);
    b3_put(err, "\n", 1);
    *nerr += 1;
  }
}

Term b3io_emit_run(Env e, Term* f, IoWork* w) {
  if (getenv("B3IO_TRACE") != NULL) {
    fprintf(stderr, "b3io hashed %8llu us after exec\n",
      (unsigned long long)(b3_us() - b3_t_start));
  }
  B3Buf out = { 0 }, err = { 0 };
  u32   nerr = 0;
  b3_emit(e, f[0], &out, &err, &nerr);
  if (out.n) {
    io_out(stdout, out.p, out.n);
  }
  if (err.n) {
    io_sync();
    io_out(stderr, err.p, err.n);
  }
  free(out.p);
  free(err.p);
  return (Term)nerr;
}

#endif

#ifdef CID(B3IO.fold)

// B3IO.fold: the XOR of every hash's eight words, so a daemon run can be
// checked against another implementation without printing. Frees the tree.
static u32 b3_fold(Env e, Term o) {
  u64 cid = term_aux(o);
  if (cid == CID(OPair)) {
    u64 at = term_peek(e.mem, o);
    return b3_fold(e, e.mem[at]) ^ b3_fold(e, e.mem[at + 1]);
  }
  if (cid == CID(OHash)) {
    u64 at = term_peek(e.mem, o);
    bool flat = cid_arity(CID(OHash)) == 9;
    u64 cv = flat ? at : term_peek(e.mem, e.mem[at]);
    u32 x = 0;
    for (u32 i = 0; i < 8; i += 1) {
      x ^= (u32)e.mem[cv + i];
    }
    return x;
  }
  return 0;
}

Term b3io_fold_run(Env e, Term* f, IoWork* w) {
  u32 x = b3_fold(e, f[0]);
  term_sink(e, f[0]);
  return (Term)x;
}

#endif

#if defined(CID(B3IO.ob_write)) || defined(CID(B3IO.ob_fold))

// Outboards
// ---------
// Bend flattens a CV record into the constructor that holds it, so ONode
// is [l0..l7, r0..r7, a, b] (arity 18) and BHash [cv0..cv7, ob, name]
// (arity 10); a boxed layout (arity 4, or 3) is read through pointers. OB
// lives in blake3.bend, past CID's reach from here, but its only other
// constructor, ONil, is nullary: a node is any constructor term.

static u64 b3_cv_at(Env e, u64 at, bool flat, u32 field) {
  return flat ? at + field * 8 : term_peek(e.mem, e.mem[at + field]);
}

// The OB tree in pre-order: this node's pair, then its left side, then its
// right side, as bao-tree lays a pre-order outboard out.
static void b3_ob_put(Env e, Term ob, B3Buf* b) {
  while (term_tag(ob) == TAG_CTR) {
    u64 at = term_peek(e.mem, ob);
    bool flat = cid_arity((u32)term_aux(ob)) == 18;
    b3_room(b, 64);
    for (u32 s = 0; s < 2; s += 1) {
      u64 cv = b3_cv_at(e, at, flat, s);
      for (u32 i = 0; i < 8; i += 1) {
        u32 x = (u32)e.mem[cv + i];
        memcpy(b->p + b->n, &x, 4);
        b->n += 4;
      }
    }
    u32 base = flat ? 16 : 2;
    b3_ob_put(e, e.mem[at + base], b);
    ob = e.mem[at + base + 1];
  }
}

static u32 b3_ob_xor(Env e, Term ob) {
  u32 x = 0;
  while (term_tag(ob) == TAG_CTR) {
    u64 at = term_peek(e.mem, ob);
    bool flat = cid_arity((u32)term_aux(ob)) == 18;
    for (u32 s = 0; s < 2; s += 1) {
      u64 cv = b3_cv_at(e, at, flat, s);
      for (u32 i = 0; i < 8; i += 1) {
        x ^= (u32)e.mem[cv + i];
      }
    }
    u32 base = flat ? 16 : 2;
    x ^= b3_ob_xor(e, e.mem[at + base]);
    ob = e.mem[at + base + 1];
  }
  return x;
}

typedef struct {
  const char* dir;
  B3Buf*      out;
  B3Buf*      err;
  u32         nerr;
} B3ObCtx;

static void b3_obo(Env e, Term o, B3ObCtx* c, u32* fold) {
  u64 cid = term_aux(o);
  if (cid == CID(BPair)) {
    u64 at = term_peek(e.mem, o);
    b3_obo(e, e.mem[at], c, fold);
    b3_obo(e, e.mem[at + 1], c, fold);
  } else if (cid == CID(BHash)) {
    u64 at = term_peek(e.mem, o);
    bool flat = cid_arity(CID(BHash)) == 10;
    u64 cv = b3_cv_at(e, at, flat, 0);
    Term ob = e.mem[at + (flat ? 8 : 1)];
    Term name = e.mem[at + (flat ? 9 : 2)];
    if (fold != NULL) {
      for (u32 i = 0; i < 8; i += 1) {
        *fold ^= (u32)e.mem[cv + i];
      }
      *fold ^= b3_ob_xor(e, ob);
      return;
    }
    b3_put_hex(e, c->out, cv);
    b3_put(c->out, "  ", 2);
    b3_put_str(e, c->out, name);
    b3_put(c->out, "\n", 1);
    B3Buf path = { 0 }, bytes = { 0 };
    b3_put(&path, c->dir, strlen(c->dir));
    b3_put(&path, "/", 1);
    u64 mark = path.n;
    b3_put_str(e, &path, name);
    char* slash = NULL;
    for (char* q = path.p + path.n; q > path.p + mark; q -= 1) {
      if (q[-1] == '/') {
        slash = q - 1;
        break;
      }
    }
    if (slash != NULL) {
      u64 tail = path.n - (u64)(slash + 1 - path.p);
      memmove(path.p + mark, slash + 1, tail);
      path.n = mark + tail;
    }
    b3_put(&path, ".obao", 6);
    b3_ob_put(e, ob, &bytes);
    FILE* fp = fopen(path.p, "wb");
    if (fp == NULL || (bytes.n && fwrite(bytes.p, 1, bytes.n, fp) != bytes.n)) {
      c->nerr += 1;
    }
    if (fp != NULL) {
      fclose(fp);
    }
    free(path.p);
    free(bytes.p);
  } else if (cid == CID(BErr) && fold == NULL) {
    u64 at = term_peek(e.mem, o);
    b3_put(c->err, "b3sum: ", 7);
    b3_put_str(e, c->err, e.mem[at + 1]);
    b3_put(c->err, ": ", 2);
    b3_put_str(e, c->err, e.mem[at]);
    b3_put(c->err, "\n", 1);
    c->nerr += 1;
  }
}

Term b3io_ob_write_run(Env e, Term* f, IoWork* w) {
  u64 n;
  char* dir = io_cstr(e, f[1], &n);
  B3Buf out = { 0 }, err = { 0 };
  B3ObCtx c = { dir, &out, &err, 0 };
  b3_obo(e, f[0], &c, NULL);
  if (out.n) {
    io_out(stdout, out.p, out.n);
  }
  if (err.n) {
    io_sync();
    io_out(stderr, err.p, err.n);
  }
  free(out.p);
  free(err.p);
  free(dir);
  term_sink(e, f[0]);
  return (Term)c.nerr;
}

Term b3io_ob_fold_run(Env e, Term* f, IoWork* w) {
  u32 x = 0;
  b3_obo(e, f[0], NULL, &x);
  term_sink(e, f[0]);
  return (Term)x;
}

#endif

static void __attribute__((constructor)) b3io_emit_use(void) {
#ifdef CID(B3IO.ob_write)
  io_eff(CID(B3IO.ob_write), b3io_ob_write_run);
#endif
#ifdef CID(B3IO.ob_fold)
  io_eff(CID(B3IO.ob_fold), b3io_ob_fold_run);
#endif
#ifdef CID(B3IO.emit)
  io_eff(CID(B3IO.emit), b3io_emit_run);
#endif
#ifdef CID(B3IO.fold)
  io_eff(CID(B3IO.fold), b3io_fold_run);
#endif
}
