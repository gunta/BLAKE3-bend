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

static void __attribute__((constructor)) b3io_emit_use(void) {
#ifdef CID(B3IO.emit)
  io_eff(CID(B3IO.emit), b3io_emit_run);
#endif
#ifdef CID(B3IO.fold)
  io_eff(CID(B3IO.fold), b3io_fold_run);
#endif
}
