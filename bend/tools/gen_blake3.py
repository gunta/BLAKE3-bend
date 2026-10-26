#!/usr/bin/env python3
"""Generates bend/blake3.bend.

Bend's `match` only destructures parameters, and a G step is eight scalar
lets, so the round body and the 16-word block loader are unrolled here
instead of by hand. Everything else in the output is plain hand-written Bend
kept verbatim in the templates below.
"""

import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "blake3.bend"

IV = [0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
      0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19]

# (a, b, c, d) state indices and the message pair each G of a round reads
G_COLS = [(0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
          (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)]

PERM = [2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8]


def fields(prefix, n=16, plus=False):
    p = "+" if plus else ""
    return ", ".join(f"{p}{prefix}{i}" for i in range(n))


def gen_round():
    """One full round (columns then diagonals) as scalar lets."""
    ver = [0] * 16
    name = lambda i: f"v{i}_{ver[i]}"
    lines = []

    def let(i, expr):
        ver[i] += 1
        lines.append(f"      +{name(i)} = {expr}")

    for g, (a, b, c, d) in enumerate(G_COLS):
        x, y = f"m{2 * g}", f"m{2 * g + 1}"
        let(a, f"({name(a)} + {name(b)} + {x} : U32)")
        let(d, f"rotr16(({name(d)} .^. {name(a)} : U32))")
        let(c, f"({name(c)} + {name(d)} : U32)")
        let(b, f"rotr12(({name(b)} .^. {name(c)} : U32))")
        let(a, f"({name(a)} + {name(b)} + {y} : U32)")
        let(d, f"rotr8(({name(d)} .^. {name(a)} : U32))")
        let(c, f"({name(c)} + {name(d)} : U32)")
        let(b, f"rotr7(({name(b)} .^. {name(c)} : U32))")
    out = ", ".join(name(i) for i in range(16))
    head = (
        "# One round: four column G steps, then four diagonal ones.\n"
        "def round(s: S16, +m: M16) -> S16:\n"
        "  match s m:\n"
        f"    case S16{{{fields('v', plus=True).replace(', ', '_0, ')}_0}} "
        f"M16{{{fields('m', plus=True)}}}:\n"
    )
    return head + "\n".join(lines) + f"\n      S16{{{out}}}\n"


def gen_loader():
    """B3.ld(a, w): the 16 words at w, as (array, M16), one read per def."""
    defs = []
    # last step: destructure word 15 and build the record
    defs.append(
        "def ld.s15(r: Array<U32> & U32, " + ", ".join(f"m{i}: U32" for i in range(15)) +
        ") -> Array<U32> & M16:\n"
        "  (a, m15) = r\n"
        f"  (a, M16{{{fields('m')}}})\n"
    )
    for k in range(14, -1, -1):
        prev = ", ".join(f"m{i}: U32" for i in range(k))
        prev_args = ", ".join(f"m{i}" for i in range(k))
        sig = f"def ld.s{k}(r: Array<U32> & U32, +w: U32" + (", " + prev if k else "") + ")"
        call_args = (prev_args + ", " if k else "") + f"m{k}"
        nxt = f"ld.s{k + 1}" if k + 1 < 15 else "ld.s15"
        if k + 1 < 15:
            body = (f"  (a, m{k}) = r\n"
                    f"  {nxt}(a[(w + {k + 1} : U32)], w, {call_args})\n")
        else:
            body = (f"  (a, m{k}) = r\n"
                    f"  {nxt}(a[(w + {k + 1} : U32)], {call_args})\n")
        defs.append(sig + " -> Array<U32> & M16:\n" + body)
    # Defs may only call defs above them: ld.s15 first, ld.0 last.
    defs.append(
        "# The 16 little-endian words of the block at word offset w.\n"
        "def ld(a: Array<U32>, +w: U32) -> Array<U32> & M16:\n"
        "  ld.s0(a[w], w)\n"
    )
    return "\n".join(defs)


# 8-lane path
# -----------
# compress8 runs eight independent compressions with every G operation
# emitted for all lanes back to back, the shape clang's SLP vectorizer packs
# into NEON registers. Lane l of a CV8 is h{l}_0..h{l}_7; of a B128,
# m{l}_0..m{l}_15.

L = 8


# Fields are word-major (word 0 of every lane, then word 1, ...): a
# compress8 that clang keeps out of line reads its arguments and writes its
# o[] results as runs of eight lanes, the seeds SLP needs for NEON vectors.
def cv8_order():
    return [(l, i) for i in range(8) for l in range(L)]


def b128_order():
    return [(l, i) for i in range(16) for l in range(L)]


def cv8_fields(prefix="h", plus=False):
    p = "+" if plus else ""
    return ", ".join(f"{p}{prefix}{l}_{i}" for l, i in cv8_order())


def b128_fields(prefix="m", plus=False):
    p = "+" if plus else ""
    return ", ".join(f"{p}{prefix}{l}_{i}" for l, i in b128_order())


def schedules():
    s = list(range(16))
    out = []
    for _ in range(7):
        out.append(s)
        s = [s[p] for p in PERM]
    return out


def gen_compress8(dname="compress8", parent=False):
    lines = []
    cur = {}
    ver = {}

    def name(l, i):
        return cur[(l, i)]

    def let(l, i, expr):
        ver[(l, i)] = ver.get((l, i), 0) + 1
        nm = f"x{l}_{i}_{ver[(l, i)]}"
        lines.append(f"      +{nm} = {expr}")
        cur[(l, i)] = nm

    for l in range(L if not parent else 0):
        lines.append(f"      +t{l} = (ctr + (step * {l} : U32) : U32)")
    for l in range(L):
        for i in range(8):
            cur[(l, i)] = f"h{l}_{i}"
        for i in range(4):
            cur[(l, 8 + i)] = str(IV[i])
        cur[(l, 12)] = "0" if parent else f"t{l}"
        cur[(l, 13)] = "0"
        cur[(l, 14)] = "blen"
        cur[(l, 15)] = "flags"
    for sched in schedules():
        for g, (a, b, c, d) in enumerate(G_COLS):
            x, y = sched[2 * g], sched[2 * g + 1]
            for (mx, r1, r2) in ((x, 16, 12), (y, 8, 7)):
                for l in range(L):
                    let(l, a, f"({name(l, a)} + {name(l, b)} + m{l}_{mx} : U32)")
                for l in range(L):
                    let(l, d, f"rotr{r1}(({name(l, d)} .^. {name(l, a)} : U32))")
                for l in range(L):
                    let(l, c, f"({name(l, c)} + {name(l, d)} : U32)")
                for l in range(L):
                    let(l, b, f"rotr{r2}(({name(l, b)} .^. {name(l, c)} : U32))")
    outs = ", ".join(f"({name(l, i)} .^. {name(l, i + 8)} : U32)"
                     for l, i in cv8_order())
    if parent:
        head = ("# compress8 for parents (counter 0): a body of its own, so each\n"
                "# copy keeps one call site and clang inlines it there.\n"
                f"def {dname}(cv: CV8, m: B128, +blen: U32, +flags: U32) -> CV8:\n")
    else:
        head = ("# Eight compressions at once; lane l's counter is ctr + step * l.\n"
                f"def {dname}(cv: CV8, m: B128, +ctr: U32, +step: U32, +blen: U32,\n"
                "  +flags: U32) -> CV8:\n")
    return (
        head +
        "  match cv m:\n"
        f"    case CV8{{{cv8_fields(plus=True)}}} B128{{{b128_fields(plus=True)}}}:\n"
        + "\n".join(lines) + f"\n      CV8{{{outs}}}\n"
    )


def gen_ld8():
    """ld8(a, w): lane l's block is ld's at w + 256 * l (eight chunks).

    Eight calls of the scalar loader, so lane l of an 8-lane block is the
    scalar block of chunk l by construction (the laws lean on it); the
    loads, and their order, are the same 128 as one flat chain."""
    ms = ", ".join(f"m{l}: M16" for l in range(L))
    pats = " ".join(
        "M16{" + ", ".join(f"m{l}_{i}" for i in range(16)) + "}" for l in range(L))
    defs = [
        "# Eight blocks, one per lane, as the word-major B128.\n"
        f"def b128.of({ms}) -> B128:\n"
        f"  match {', '.join(f'm{l}' for l in range(L)).replace(',', '')}:\n"
        f"    case {pats}:\n"
        f"      B128{{{b128_fields()}}}\n"
    ]
    prev = ", ".join(f"m{l}: M16" for l in range(L - 1))
    defs.append(
        f"def ld8.s{L - 1}(r: Array<U32> & M16, {prev}) -> Array<U32> & B128:\n"
        f"  (a, m{L - 1}) = r\n"
        f"  (a, b128.of({', '.join(f'm{l}' for l in range(L))}))\n"
    )
    for k in range(L - 2, -1, -1):
        params = ", ".join(f"m{l}: M16" for l in range(k))
        args = ", ".join(f"m{l}" for l in range(k + 1))
        nxt = k + 1
        sig = f"def ld8.s{k}(r: Array<U32> & M16, +w: U32" + (", " + params if k else "") + ")"
        if nxt == L - 1:
            call = f"  ld8.s{nxt}(ld(a, (w + {256 * nxt} : U32)), {args})\n"
        else:
            call = f"  ld8.s{nxt}(ld(a, (w + {256 * nxt} : U32)), w, {args})\n"
        defs.append(sig + " -> Array<U32> & B128:\n" + f"  (a, m{k}) = r\n" + call)
    defs.append(
        "# The blocks at word w of eight consecutive chunks.\n"
        "def ld8(a: Array<U32>, +w: U32) -> Array<U32> & B128:\n"
        "  ld8.s0(ld(a, w), w)\n"
    )
    return "\n".join(defs)


def gen_par8():
    # lane j < 4: parent of x's lanes 2j, 2j+1; lane 4 + j: of y's.
    val = {}
    for j in range(L):
        src, base = ("x", 2 * j) if j < 4 else ("y", 2 * (j - 4))
        for i in range(8):
            val[(j, i)] = f"{src}{base}_{i}"
            val[(j, 8 + i)] = f"{src}{base + 1}_{i}"
    msg = [val[k] for k in b128_order()]
    xs = cv8_fields("x")
    ys = cv8_fields("y")
    return (
        "# One level of parents over 16 CVs: lanes 0-3 merge x's lane pairs,\n"
        "# lanes 4-7 merge y's, so a level stays in lane order.\n"
        "def par8(x: CV8, y: CV8) -> CV8:\n"
        "  match x y:\n"
        f"    case CV8{{{xs}}} CV8{{{ys}}}:\n"
        f"      compress8.p(IV8(), B128{{{', '.join(msg)}}}, 64, PARENT())\n"
    )


def gen_fold8():
    xs = cv8_fields("x")
    cv = lambda l: "CV{" + ", ".join(f"x{l}_{i}" for i in range(8)) + "}"
    return (
        "# The last three levels over a CV8's lanes, one compression each.\n"
        "def fold8(x: CV8, +rf: U32) -> CV:\n"
        "  match x:\n"
        f"    case CV8{{{xs}}}:\n"
        f"      parent(parent(parent({cv(0)}, {cv(1)}, 0), parent({cv(2)}, {cv(3)}, 0), 0),\n"
        f"        parent(parent({cv(4)}, {cv(5)}, 0), parent({cv(6)}, {cv(7)}, 0), 0), rf)\n"
    )


def gen_keyed8():
    """The 8-lane tree in BLAKE3's keyed and key-derivation modes: the
    default mode's defs with the key (in every lane: key8) and the mode flag
    threaded through, compress8 unchanged. hash8.at.k is the entry point."""
    k8 = ", ".join(f"h{i}" for l, i in cv8_order())
    par8 = gen_par8().replace(
        "def par8(x: CV8, y: CV8) -> CV8:", "def par8.k(x: CV8, y: CV8, +key: CV, +kf: U32) -> CV8:"
    ).replace("compress8.p(IV8(), ", "compress8.p(key8(key), ").replace(
        ", 64, PARENT())", ", 64, (PARENT() .|. kf : U32))")
    fold8 = gen_fold8().replace(
        "def fold8(x: CV8, +rf: U32) -> CV:", "def fold8.k(x: CV8, +rf: U32, +key: CV, +kf: U32) -> CV:"
    ).replace(", 0)", ", 0, key, kf)").replace(", rf)", ", rf, key, kf)").replace("parent(", "parent.k(")
    for old in ("def par8(", "def fold8(", "IV8()", ", PARENT())"):
        assert old not in par8 + fold8, old
    return f"""
# Keyed and key-derivation modes, 8 lanes
# ---------------------------------------
#
# The CPU tree's defs again, with the key (`key`, and `k8` in every lane)
# and the mode flag (kf) threaded through, as the scalar .k defs do;
# compress8 and the node kinds are the default mode's.

def key8(+k: CV) -> CV8:
  match k:
    case CV{{{", ".join(f"+h{i}" for i in range(8))}}}:
      CV8{{{k8}}}

def c8.go.k(+n: Nat, r: Array<U32> & B128, +w: U32, cv: CV8, +ctr: U32,
  +fl: U32, +kf: U32) -> Array<U32> & CV8:
  match n:
    case 0n:
      (a, m) = r
      (a, cv)
    case 1n+p:
      (a, m) = r
      +w2 = (w + step(p) : U32)
      c8.go.k(p, ld8(a, w2), w2, compress8(cv, m, ctr, 1, 64,
        ((fl .|. endf(p) : U32) .|. kf : U32)), ctr, 0, kf)

def group.k(a: Array<U32>, +c: U32, +t: U32, +key: CV, +kf: U32) -> Array<U32> & CV8:
  +w = (c << 8n : U32)
  c8.go.k(16n, ld8(a, w), w, key8(key), t, CHUNK_START(), kf)

{par8}
{fold8}
def leaf8.fin.k(r: Array<U32> & CV8, +rf: U32, +key: CV, +kf: U32) -> CV:
  (a, x) = r
  _ = a
  fold8.k(x, rf, key, kf)

def leaf8.k(a: Array<U32>, +c: U32, +t: U32, +rf: U32, +key: CV, +kf: U32) -> CV:
  leaf8.fin.k(group.k(a, c, t, key, kf), rf, key, kf)

def leaf32.s3.k(r: Array<U32> & CV8, x: CV8, g2: CV8, +key: CV, +kf: U32) -> Array<U32> & CV8:
  (a, g3) = r
  (a, par8.k(x, par8.k(g2, g3, key, kf), key, kf))

def leaf32.s2.k(r: Array<U32> & CV8, +c: U32, +t: U32, x: CV8, +key: CV, +kf: U32) -> Array<U32> & CV8:
  (a, g2) = r
  leaf32.s3.k(group.k(a, (c + 24 : U32), (t + 24 : U32), key, kf), x, g2, key, kf)

def leaf32.s1.k(r: Array<U32> & CV8, +c: U32, +t: U32, g0: CV8, +key: CV, +kf: U32) -> Array<U32> & CV8:
  (a, g1) = r
  leaf32.s2.k(group.k(a, (c + 16 : U32), (t + 16 : U32), key, kf), c, t, par8.k(g0, g1, key, kf), key, kf)

def leaf32.s0.k(r: Array<U32> & CV8, +c: U32, +t: U32, +key: CV, +kf: U32) -> Array<U32> & CV8:
  (a, g0) = r
  leaf32.s1.k(group.k(a, (c + 8 : U32), (t + 8 : U32), key, kf), c, t, g0, key, kf)

def leaf32.k(a: Array<U32>, +c: U32, +t: U32, +rf: U32, +key: CV, +kf: U32) -> CV:
  leaf8.fin.k(leaf32.s0.k(group.k(a, c, t, key, kf), c, t, key, kf), rf, key, kf)

def tree8.k(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, +ku: U32, d: Node, aa: Array<U32> & Array<U32>, +c: U32,
  +n: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, +key: CV,
  +kf: U32) -> CV:
  match k d:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      chunk.k(a1, c, cb, nch, last, rf, key, kf)
    case 1n+p Down{{}}:
      +kp = (ku - 1 : U32)
      tree8.k(~dup, p, kp, kind(kp, n, c, nch, last), aa, c, n, cb, nch, last, rf, key, kf)
    case 1n+p Leaf32{{}}:
      (a1, a2) = aa
      _ = a2
      leaf32.k(a1, c, (cb + c : U32), rf, key, kf)
    case 1n+p Leaf8{{}}:
      (a1, a2) = aa
      _ = a2
      leaf8.k(a1, c, (cb + c : U32), rf, key, kf)
    case 1n+p Split{{}}:
      (a1, a2) = aa
      +kp = (ku - 1 : U32)
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      +c2 = (c + h : U32)
      l r = tree8.k(~dup, p, kp, kind(kp, h, c, nch, last), dup(a1), c, h, cb, nch, last, 0, key, kf) tree8.k(~dup, p, kp, kind(kp, n2, c2, nch, last), dup(a2), c2, n2, cb, nch, last, 0, key, kf)
      parent.k(l, r, rf, key, kf)

def hash8.go.k(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +cb: U32, +nch: U32, +last: U32,
  +rf: U32, +key: CV, +kf: U32) -> CV:
  match k:
    case 0n:
      chunk.k(a, 0, cb, nch, last, rf, key, kf)
    case 1n+p:
      +ku = U32.from_nat(k)
      tree8.k(~dup, k, ku, kind(ku, nch, 0, nch, last), dup(a), 0, nch, cb,
        nch, last, rf, key, kf)

# The CV of a span (as hash.at) in any mode, on the CPU's 8-lane tree.
def hash8.at.k(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32, +key: CV, +kf: U32) -> CV:
  hash8.go.k(~dup, depth(nch), a, cb, nch, last, rf, key, kf)
"""


def gen_quad(name, sub, size):
    """name(a, c, t, rf): four sub-leaves of `size` chunks each, in order,
    then two levels of parents (the last takes rf). No forks: one GPU lane
    runs it start to end."""
    S = size
    return f"""def {name}.s3(r: Array<U32> & CV, y: CV, x2: CV, +rf: U32) -> Array<U32> & CV:
  (a, x3) = r
  (a, parent(y, parent(x2, x3, 0), rf))

def {name}.s2(r: Array<U32> & CV, +c: U32, +t: U32, y: CV, +rf: U32) -> Array<U32> & CV:
  (a, x2) = r
  {name}.s3({sub}(a, (c + {3 * S} : U32), (t + {3 * S} : U32), 0), y, x2, rf)

def {name}.s1(r: Array<U32> & CV, +c: U32, +t: U32, x0: CV, +rf: U32) -> Array<U32> & CV:
  (a, x1) = r
  {name}.s2({sub}(a, (c + {2 * S} : U32), (t + {2 * S} : U32), 0), c, t, parent(x0, x1, 0), rf)

def {name}.s0(r: Array<U32> & CV, +c: U32, +t: U32, +rf: U32) -> Array<U32> & CV:
  (a, x0) = r
  {name}.s1({sub}(a, (c + {S} : U32), (t + {S} : U32), 0), c, t, x0, rf)

def {name}(a: Array<U32>, +c: U32, +t: U32, +rf: U32) -> Array<U32> & CV:
  {name}.s0({sub}(a, c, t, 0), c, t, rf)
"""


GPU_LEAVES = """
# GPU leaves
# ----------
# One full chunk, then 4, 16 and 64 full chunks in order, each a chain with
# no fork: the GPU tree forks down to 64-chunk subtrees and every lane hashes
# one start to end, the shape the shaders guide asks for (one flat task per
# lane), instead of a task per chunk.

# A full chunk at array chunk c, counter t; rf ignored (a quad's leaf).
def gch(a: Array<U32>, +c: U32, +t: U32, +rf: U32) -> Array<U32> & CV:
  +w = (c << 8n : U32)
  chunk.go(15n, ld(a, w), w, IV(), t, CHUNK_START(), CHUNK_END(), 64)

""" + gen_quad("g4", "gch", 1) + "\n" + gen_quad("g16", "g4", 4) + "\n" + \
    gen_quad("g64", "g16", 16) + """
def g.fin(r: Array<U32> & CV) -> CV:
  (a, cv) = r
  _ = a
  cv

# Strided lanes for big subtrees
# ------------------------------
# 64-chunk leaves make 16384 lanes stream 16384 separate 64 KiB runs spread
# over the input, and the GPU reads that at 2/3 of what it can (ADR 0006).
# So at that leaf level a whole subtree of 64 S chunks goes to S lanes (as
# many as its leaves) that read neighbouring memory: lane l hashes the
# 16-chunk groups l, l + S, l + 2S and l + 3S, so the lanes running together
# read one window of 16 S KiB (ADR 0011). The fork over the lanes is the
# tree over lane numbers, and a join pairs its halves' four CVs group for
# group: BLAKE3's tree of groups, level by level (the `levels` law), so
# after log2(S) joins the four CVs are the subtree's quarters.

# Four CVs, one per quarter of a subtree, in order.
type CV4 is Data:
  CV4{a: CV, b: CV, c: CV, d: CV}

def quad.s3(r: Array<U32> & CV, x0: CV, x1: CV, x2: CV) -> CV4:
  (a, x3) = r
  _ = a
  CV4{x0, x1, x2, x3}

def quad.s2(r: Array<U32> & CV, +c: U32, +t: U32, +st: U32, x0: CV, x1: CV) ->
  CV4:
  (a, x2) = r
  +s3 = (st + (st << 1n : U32) : U32)
  quad.s3(g16(a, (c + s3 : U32), (t + s3 : U32), 0), x0, x1, x2)

def quad.s1(r: Array<U32> & CV, +c: U32, +t: U32, +st: U32, x0: CV) -> CV4:
  (a, x1) = r
  +s2 = (st << 1n : U32)
  quad.s2(g16(a, (c + s2 : U32), (t + s2 : U32), 0), c, t, st, x0, x1)

def quad.s0(r: Array<U32> & CV, +c: U32, +t: U32, +st: U32) -> CV4:
  (a, x0) = r
  quad.s1(g16(a, (c + st : U32), (t + st : U32), 0), c, t, st, x0)

# One lane: the 16-chunk groups at array chunks c, c + st, c + 2st and
# c + 3st (counters t, t + st, ...).
def quad(a: Array<U32>, +c: U32, +t: U32, +st: U32) -> CV4:
  quad.s0(g16(a, c, t, 0), c, t, st)

def par4(x: CV4, y: CV4) -> CV4:
  match x y:
    case CV4{x0, x1, x2, x3} CV4{y0, y1, y2, y3}:
      CV4{parent(x0, y0, 0), parent(x1, y1, 0), parent(x2, y2, 0),
        parent(x3, y3, 0)}

def fold4(x: CV4, +rf: U32) -> CV:
  match x:
    case CV4{x0, x1, x2, x3}:
      parent(parent(x0, x1, 0), parent(x2, x3, 0), rf)

# 2^k lanes from the one whose first group is at array chunk c (counter t),
# st chunks between a lane's groups.
def qtree(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, aa: Array<U32> & Array<U32>, +c: U32, +t: U32, +st: U32) -> CV4:
  match k:
    case 0n:
      (a1, a2) = aa
      _ = a2
      quad(a1, c, t, st)
    case 1n+p:
      (a1, a2) = aa
      +h = U32.shln(16, p)
      l r = qtree(~dup, p, dup(a1), c, t, st) qtree(~dup, p, dup(a2), (c + h : U32), (t + h : U32), st)
      par4(l, r)

# Whether chunks up to e (exclusive) are all full: the last chunk, nch - 1,
# holds `last` bytes.
def full(+e: U32, +nch: U32, +last: U32) -> Bool:
  U32.is_lt(e, nch) || (U32.is_eq(e, nch) && U32.is_eq(last, 1024))

type Node1 is Data:
  GDown{}
  GSplit{}
  G4{}
  G16{}
  G64{}
  GQuad{}

def kind1.at4(b: Bool) -> Node1:
  match b:
    case True{}:
      G4{}
    case False{}:
      GSplit{}

def kind1.at16(b: Bool, +k: U32) -> Node1:
  match b:
    case True{}:
      G16{}
    case False{}:
      kind1.at4(U32.is_eq(k, 2))

def kind1.at64(b: Bool, +k: U32) -> Node1:
  match b:
    case True{}:
      G64{}
    case False{}:
      kind1.at16(U32.is_eq(k, 4), k)

def kind1.full(+k: U32, full: Bool) -> Node1:
  match full:
    case False{}:
      GSplit{}
    case True{}:
      kind1.at64(U32.is_eq(k, 6), k)

def kind1.wq(q: Bool, +k: U32, +lv: U32) -> Node1:
  match q:
    case True{}:
      GQuad{}
    case False{}:
      kind1.full(k, U32.is_le(k, lv))

def kind1.whole(+k: U32, +lv: U32, whole: Bool) -> Node1:
  match whole:
    case False{}:
      GSplit{}
    case True{}:
      kind1.wq(U32.is_eq(lv, 6) && U32.is_gt(k, 6), k, lv)

def kind1.big(+k: U32, +n: U32, +c: U32, +nch: U32, +last: U32, +lv: U32,
  b: Bool) -> Node1:
  match b:
    case False{}:
      GDown{}
    case True{}:
      kind1.whole(k, lv, U32.is_eq(n, U32.shln(1, U32.to_nat(k))) &&
        full((c + n : U32), nch, last))

# The kind of a node of depth k >= 1 of the GPU tree: a full subtree of
# 4, 16 or 64 chunks, no deeper than the leaf level lv, is one lane's leaf;
# at leaf level 6 a bigger whole subtree goes to strided lanes instead, as
# many as its 64-chunk leaves would take.
def kind1(+k: U32, +n: U32, +c: U32, +nch: U32, +last: U32, +lv: U32) -> Node1:
  kind1.big(k, n, c, nch, last, lv,
    U32.is_gt(n, U32.shln(1, U32.to_nat((k - 1 : U32)))))

# The leaf level for an input of depth k: the GPU runs 2^14 lanes, so
# leaves of 2^(k - 14) chunks (rounded down to 4^j, at most 64) keep every
# lane busy without a task per chunk.
def level(+k: U32) -> U32:
  +l = U32.min(U32.max(k, 14), 20)
  (((l - 14 : U32) >> 1n : U32) << 1n : U32)

# The GPU tree: forks to full 64-, 16- or 4-chunk subtrees, one lane each,
# and at leaf level 6 hands bigger whole subtrees to strided lanes.
def treeg(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, +ku: U32, d: Node1, aa: Array<U32> & Array<U32>, +c: U32,
  +n: U32, +cb: U32, +nch: U32, +last: U32, +lv: U32, +rf: U32) -> CV:
  match k d:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      chunk(a1, c, cb, nch, last, rf)
    case 1n+p GDown{}:
      +kp = (ku - 1 : U32)
      treeg(~dup, p, kp, kind1(kp, n, c, nch, last, lv), aa, c, n, cb, nch, last, lv, rf)
    case 1n+p GQuad{}:
      (a1, a2) = aa
      _ = a2
      +q = U32.to_nat((ku - 6 : U32))
      fold4(qtree(~dup, q, dup(a1), c, (cb + c : U32), U32.shln(16, q)), rf)
    case 1n+p G64{}:
      (a1, a2) = aa
      _ = a2
      g.fin(g64(a1, c, (cb + c : U32), rf))
    case 1n+p G16{}:
      (a1, a2) = aa
      _ = a2
      g.fin(g16(a1, c, (cb + c : U32), rf))
    case 1n+p G4{}:
      (a1, a2) = aa
      _ = a2
      g.fin(g4(a1, c, (cb + c : U32), rf))
    case 1n+p GSplit{}:
      (a1, a2) = aa
      +kp = (ku - 1 : U32)
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      +c2 = (c + h : U32)
      l r = treeg(~dup, p, kp, kind1(kp, h, c, nch, last, lv), dup(a1), c, h, cb, nch, last, lv, 0) treeg(~dup, p, kp, kind1(kp, n2, c2, nch, last, lv), dup(a2), c2, n2, cb, nch, last, lv, 0)
      parent(l, r, rf)
"""


WIDE = """
type CV8 is Data:
  CV8{{{cv8}}}

type B128 is Data:
  B128{{{b128}}}

def IV8() -> CV8:
  CV8{{{iv8}}}

{ld8}
{compress8}
{compress8p}
def endf(+p: Nat) -> U32:
  match p:
    case 0n:
      CHUNK_END()
    case 1n+q:
      0

# The step to the next block: none after the last, so the loop's one extra
# load re-reads a block of the chunks instead of reading past them (a
# mapped file may end right there).
def step(+p: Nat) -> U32:
  match p:
    case 0n:
      0
    case 1n+q:
      16

# Chains eight full chunks from word w at once; n counts the blocks left.
# The loop has one compress8, so clang inlines it and vectorizes the whole
# loop from the word-major stores of its result. At n = 0, r holds a block
# read for nothing.
def c8.go(+n: Nat, r: Array<U32> & B128, +w: U32, cv: CV8, +ctr: U32,
  +fl: U32) -> Array<U32> & CV8:
  match n:
    case 0n:
      (a, m) = r
      (a, cv)
    case 1n+p:
      (a, m) = r
      +w2 = (w + step(p) : U32)
      c8.go(p, ld8(a, w2), w2, compress8(cv, m, ctr, 1, 64,
        (fl .|. endf(p) : U32)), ctr, 0)

# The CVs of chunks c..c+7 of the array, whose counters start at t.
def group(a: Array<U32>, +c: U32, +t: U32) -> Array<U32> & CV8:
  +w = (c << 8n : U32)
  c8.go(16n, ld8(a, w), w, IV8(), t, CHUNK_START())

{par8}
{fold8}
def leaf8.fin(r: Array<U32> & CV8, +rf: U32) -> CV:
  (a, x) = r
  _ = a
  fold8(x, rf)

def leaf8(a: Array<U32>, +c: U32, +t: U32, +rf: U32) -> CV:
  leaf8.fin(group(a, c, t), rf)

# 32 full chunks: four groups, two levels of par8, then fold8.
def leaf32.s3(r: Array<U32> & CV8, x: CV8, g2: CV8) -> Array<U32> & CV8:
  (a, g3) = r
  (a, par8(x, par8(g2, g3)))

def leaf32.s2(r: Array<U32> & CV8, +c: U32, +t: U32, x: CV8) -> Array<U32> & CV8:
  (a, g2) = r
  leaf32.s3(group(a, (c + 24 : U32), (t + 24 : U32)), x, g2)

def leaf32.s1(r: Array<U32> & CV8, +c: U32, +t: U32, g0: CV8) -> Array<U32> & CV8:
  (a, g1) = r
  leaf32.s2(group(a, (c + 16 : U32), (t + 16 : U32)), c, t, par8(g0, g1))

def leaf32.s0(r: Array<U32> & CV8, +c: U32, +t: U32) -> Array<U32> & CV8:
  (a, g0) = r
  leaf32.s1(group(a, (c + 8 : U32), (t + 8 : U32)), c, t, g0)

def leaf32(a: Array<U32>, +c: U32, +t: U32, +rf: U32) -> CV:
  leaf8.fin(leaf32.s0(group(a, c, t), c, t), rf)

# What a node of the CPU tree does.
type Node is Data:
  Down{{}}
  Split{{}}
  Leaf8{{}}
  Leaf32{{}}

def kind.at3(b: Bool) -> Node:
  match b:
    case True{{}}:
      Leaf8{{}}
    case False{{}}:
      Split{{}}

def kind.at(b: Bool, +k: U32) -> Node:
  match b:
    case True{{}}:
      Leaf32{{}}
    case False{{}}:
      kind.at3(U32.is_eq(k, 3))

def kind.full(+k: U32, full: Bool) -> Node:
  match full:
    case False{{}}:
      Split{{}}
    case True{{}}:
      kind.at(U32.is_eq(k, 5), k)

def kind.big(+k: U32, +n: U32, +c: U32, +nch: U32, +last: U32, b: Bool) -> Node:
  match b:
    case False{{}}:
      Down{{}}
    case True{{}}:
      kind.full(k, U32.is_eq(n, U32.shln(1, U32.to_nat(k))) &&
        full((c + n : U32), nch, last))

# The kind of a node of depth k >= 1 over chunks c..c+n: a wide leaf needs
# all 2^k chunks full.
def kind(+k: U32, +n: U32, +c: U32, +nch: U32, +last: U32) -> Node:
  kind.big(k, n, c, nch, last,
    U32.is_gt(n, U32.shln(1, U32.to_nat((k - 1 : U32)))))

# tree1's shape, but full 32- and 8-chunk subtrees go through compress8.
def tree8(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, +ku: U32, d: Node, aa: Array<U32> & Array<U32>, +c: U32,
  +n: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV:
  match k d:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      chunk(a1, c, cb, nch, last, rf)
    case 1n+p Down{{}}:
      +kp = (ku - 1 : U32)
      tree8(~dup, p, kp, kind(kp, n, c, nch, last), aa, c, n, cb, nch, last, rf)
    case 1n+p Leaf32{{}}:
      (a1, a2) = aa
      _ = a2
      leaf32(a1, c, (cb + c : U32), rf)
    case 1n+p Leaf8{{}}:
      (a1, a2) = aa
      _ = a2
      leaf8(a1, c, (cb + c : U32), rf)
    case 1n+p Split{{}}:
      (a1, a2) = aa
      +kp = (ku - 1 : U32)
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      +c2 = (c + h : U32)
      l r = tree8(~dup, p, kp, kind(kp, h, c, nch, last), dup(a1), c, h, cb, nch, last, 0) tree8(~dup, p, kp, kind(kp, n2, c2, nch, last), dup(a2), c2, n2, cb, nch, last, 0)
      parent(l, r, rf)

# Entry points
# ------------
#
# An input is a span: nch chunks held from word 0 of an array, the last
# holding `last` bytes (1..1024, or 0 for the empty input), with chunk
# counters from cb. A whole input takes rf = ROOT; a span that is a
# complete subtree of a larger input (a 1 GiB segment of a big file) takes
# rf = 0 and gives that subtree's CV.
#
# The trees and entry points take `~dup`, which hands a tree node two read
# handles of the input. hash.bend passes Array.fork (O(1), the fast path,
# but @unsafe in Base); the laws pass Array.clone, so every def in this file
# is proof-safe and LAWS.bend states facts about the code that runs.

def hash.go(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +cb: U32, +nch: U32, +last: U32,
  +rf: U32) -> CV:
  match k:
    case 0n:
      chunk(a, 0, cb, nch, last, rf)
    case 1n+p:
      +ku = U32.from_nat(k)
      tree8(~dup, k, ku, kind(ku, nch, 0, nch, last), dup(a), 0, nch, cb,
        nch, last, rf)

# The CV of a span, on the CPU's 8-lane tree.
def hash.at(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV:
  hash.go(~dup, depth(nch), a, cb, nch, last, rf)

# The bytes of the last chunk of a len-byte input of n chunks.
def tail(+len: U32, +n: U32) -> U32:
  (len - ((n - 1 : U32) << 10n : U32) : U32)

# The BLAKE3 hash (first 32 bytes) of `len` bytes held in `a`, for the CPU.
def hash(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +len: U32) -> CV:
  +n = chunks(len)
  hash.at(~dup, a, 0, n, tail(len, n), ROOT())

# Bao outboards
# -------------
#
# iroh-blobs (bao-tree) stores, beside a blob, the pair (left CV, right CV)
# of every parent above its 16 KiB chunk groups, in pre-order: a blob of B
# groups has B - 1 pairs. A group is 2^4 chunks, so those are BLAKE3's own
# parents of level 5 and up (each child at least a whole group). tree8o is
# tree8 that keeps them as an OB tree (the pair, then the left side's pairs,
# then the right side's), as it computes them.

type OB is Data:
  ONil{{}}
  ONode{{l: CV, r: CV, a: OB, b: OB}}

def join.pick(rec: Bool, +l: CV, +r: CV, a: OB, b: OB, +rf: U32) -> CV & OB:
  match rec:
    case True{{}}:
      (parent(l, r, rf), ONode{{l, r, a, b}})
    case False{{}}:
      (parent(l, r, rf), ONil{{}})

# A parent over two subtrees' results; rec says whether it is an outboard
# node (both children at least a chunk group).
def join.o(x: CV & OB, y: CV & OB, +rf: U32, rec: Bool) -> CV & OB:
  (l, a) = x
  (r, b) = y
  join.pick(rec, l, r, a, b, rf)

# fold8 that keeps its top parent: over a CV8 of 4-chunk subtrees, that
# parent's children are the two 16-chunk groups.
def fold8o(x: CV8, +rf: U32) -> CV & OB:
  match x:
    case CV8{{{cv8f}}}:
      +gl = parent(parent({c0}, {c1}, 0), parent({c2}, {c3}, 0), 0)
      +gr = parent(parent({c4}, {c5}, 0), parent({c6}, {c7}, 0), 0)
      (parent(gl, gr, rf), ONode{{gl, gr, ONil{{}}, ONil{{}}}})

def leaf32o.fin(r: Array<U32> & CV8, +rf: U32) -> CV & OB:
  (a, x) = r
  _ = a
  fold8o(x, rf)

def leaf32o(a: Array<U32>, +c: U32, +t: U32, +rf: U32) -> CV & OB:
  leaf32o.fin(leaf32.s0(group(a, c, t), c, t), rf)

def tree8o(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, +ku: U32, d: Node, aa: Array<U32> & Array<U32>, +c: U32,
  +n: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV & OB:
  match k d:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      (chunk(a1, c, cb, nch, last, rf), ONil{{}})
    case 1n+p Down{{}}:
      +kp = (ku - 1 : U32)
      tree8o(~dup, p, kp, kind(kp, n, c, nch, last), aa, c, n, cb, nch, last, rf)
    case 1n+p Leaf32{{}}:
      (a1, a2) = aa
      _ = a2
      leaf32o(a1, c, (cb + c : U32), rf)
    case 1n+p Leaf8{{}}:
      (a1, a2) = aa
      _ = a2
      (leaf8(a1, c, (cb + c : U32), rf), ONil{{}})
    case 1n+p Split{{}}:
      (a1, a2) = aa
      +kp = (ku - 1 : U32)
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      +c2 = (c + h : U32)
      x y = tree8o(~dup, p, kp, kind(kp, h, c, nch, last), dup(a1), c, h, cb, nch, last, 0) tree8o(~dup, p, kp, kind(kp, n2, c2, nch, last), dup(a2), c2, n2, cb, nch, last, 0)
      join.o(x, y, rf, U32.is_ge(ku, 5))

def hash.ob.go(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +cb: U32, +nch: U32, +last: U32,
  +rf: U32) -> CV & OB:
  match k:
    case 0n:
      (chunk(a, 0, cb, nch, last, rf), ONil{{}})
    case 1n+p:
      +ku = U32.from_nat(k)
      tree8o(~dup, k, ku, kind(ku, nch, 0, nch, last), dup(a), 0, nch,
        cb, nch, last, rf)

# The CV of a span, with its outboard pairs (see above).
def hash.ob.at(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV & OB:
  hash.ob.go(~dup, depth(nch), a, cb, nch, last, rf)

def hash.ob(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +len: U32) -> CV & OB:
  +n = chunks(len)
  hash.ob.at(~dup, a, 0, n, tail(len, n), ROOT())

def hash1.go(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +cb: U32, +nch: U32, +last: U32,
  +rf: U32) -> CV:
  match k:
    case 0n:
      chunk(a, 0, cb, nch, last, rf)
    case 1n+p:
      +ku = U32.from_nat(k)
      +lv = level(ku)
      treeg(~dup, k, ku, kind1(ku, nch, 0, nch, last, lv), dup(a), 0,
        nch, cb, nch, last, lv, rf)

# The CV of a span, one lane per chunk: the shape for the GPU (call with !).
def hash1.at(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV:
  hash1.go(~dup, depth(nch), a, cb, nch, last, rf)

def hash1(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +len: U32) -> CV:
  +n = chunks(len)
  hash1.at(~dup, a, 0, n, tail(len, n), ROOT())
"""


HEADER = '''\
# BLAKE3 in Bend2
# ===============
#
# GENERATED by tools/gen_blake3.py: edit the generator, not this file.
#
# The input is an Array<U32> of little-endian words, zero-padded past `len`
# up to the end of its last 64-byte block. The hash is the BLAKE3 tree: every
# 1024-byte chunk is chained through its 16 blocks, then chunk CVs merge
# pairwise up a left-full binary tree. The tree's two halves are a parallel
# let, so `H.hash` (hash.bend) runs on every CPU core and `H.hash1!` on the
# GPU.

import Base

# Records of scalars ride in registers: a CV or a block never touches the heap.
type CV is Data:
  CV{{h0: U32, h1: U32, h2: U32, h3: U32, h4: U32, h5: U32, h6: U32, h7: U32}}

type M16 is Data:
  M16{{{m16}}}

type S16 is Data:
  S16{{{s16}}}

# Flags
def CHUNK_START() -> U32:
  1

def CHUNK_END() -> U32:
  2

def PARENT() -> U32:
  4

def ROOT() -> U32:
  8

def IV() -> CV:
  CV{{{iv}}}

def rotr16(+x: U32) -> U32:
  ((x >> 16n) .|. (x << 16n) : U32)

def rotr12(+x: U32) -> U32:
  ((x >> 12n) .|. (x << 20n) : U32)

def rotr8(+x: U32) -> U32:
  ((x >> 8n) .|. (x << 24n) : U32)

def rotr7(+x: U32) -> U32:
  ((x >> 7n) .|. (x << 25n) : U32)

'''

AFTER_ROUND = '''
# The message schedule between rounds.
def perm(m: M16) -> M16:
  match m:
    case M16{{{mf}}}:
      M16{{{perm}}}

def out(s: S16) -> CV:
  match s:
    case S16{{{sf}}}:
      CV{{{cvout}}}

# The compression function, truncated to the 8 words a CV needs.
def compress(cv: CV, +m1: M16, +t0: U32, +t1: U32, +blen: U32, +flags: U32) -> CV:
  match cv:
    case CV{{h0, h1, h2, h3, h4, h5, h6, h7}}:
      +m2 = perm(m1)
      +m3 = perm(m2)
      +m4 = perm(m3)
      +m5 = perm(m4)
      +m6 = perm(m5)
      +m7 = perm(m6)
      s0 = {{S16{{h0, h1, h2, h3, h4, h5, h6, h7, {iv4}, t0, t1, blen, flags}} : S16}}
      out(round(round(round(round(round(round(round(s0, m1), m2), m3), m4), m5), m6), m7))

'''

TREE = '''
# Chains one chunk's blocks. `r` is the block at word w, already loaded; n
# counts the blocks after it. Only the last block takes `endf` and `lastlen`.
def chunk.go(n: Nat, r: Array<U32> & M16, +w: U32, cv: CV, +ctr: U32, +fl: U32,
  +endf: U32, +lastlen: U32) -> Array<U32> & CV:
  match n:
    case 0n:
      (a, m) = r
      (a, compress(cv, m, ctr, 0, lastlen, (fl .|. endf : U32)))
    case 1n+p:
      (a, m) = r
      +w2 = (w + 16 : U32)
      chunk.go(p, ld(a, w2), w2, compress(cv, m, ctr, 0, 64, fl), ctr, 0, endf,
        lastlen)

def chunk.fin(r: Array<U32> & CV) -> CV:
  (a, cv) = r
  _ = a
  cv

# The CV of chunk c of a span (see hash.at); rf is ROOT for a one-chunk
# input. Every chunk holds 1024 bytes but the span's last, which holds last.
def chunk(a: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32,
  +rf: U32) -> CV:
  +w = (c << 8n : U32)
  +m = (0 - Bool.to_u32(U32.is_eq((c + 1 : U32), nch)) : U32)
  +rem = ((last .&. m) .|. (1024 .&. U32.not(m)) : U32)
  +nb = U32.max(((rem + 63 : U32) >> 6n : U32), 1)
  +lastlen = (rem - ((nb - 1 : U32) << 6n : U32) : U32)
  chunk.fin(chunk.go(U32.to_nat((nb - 1 : U32)), ld(a, w), w, IV(),
    (cb + c : U32), CHUNK_START(), (CHUNK_END() .|. rf : U32), lastlen))

def parent(l: CV, r: CV, +rf: U32) -> CV:
  match l r:
    case CV{l0, l1, l2, l3, l4, l5, l6, l7} CV{r0, r1, r2, r3, r4, r5, r6, r7}:
      compress(IV(), M16{l0, l1, l2, l3, l4, l5, l6, l7, r0, r1, r2, r3, r4, r5,
        r6, r7}, 0, 0, 64, (PARENT() .|. rf : U32))

# Whether n chunks overflow a left subtree of 2^(k-1): if so, a level of
# depth k has a parent node.
def big(+k: Nat, +n: U32) -> Bool:
  match k:
    case 0n:
      False{}
    case 1n+p:
      U32.is_gt(n, U32.shln(1, p))

# The CV of the n chunks from chunk c, n <= 2^k. Each node holds two read
# handles of the input (dup: an O(1) Array.fork in hash.bend), so both
# halves read it at once.
def tree1(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, b: Bool, aa: Array<U32> & Array<U32>, +c: U32, +n: U32,
  +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV:
  match k b:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      chunk(a1, c, cb, nch, last, rf)
    case 1n+p False{}:
      tree1(~dup, p, big(p, n), aa, c, n, cb, nch, last, rf)
    case 1n+p True{}:
      (a1, a2) = aa
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      l r = tree1(~dup, p, big(p, h), dup(a1), c, h, cb, nch, last, 0) tree1(~dup, p, big(p, n2), dup(a2), (c + h : U32), n2, cb, nch, last, 0)
      parent(l, r, rf)

def chunks(+len: U32) -> U32:
  U32.max(((len + 1023 : U32) >> 10n : U32), 1)

# ceil(log2(n)) for n >= 1
def depth.go(b: Bool, +n: U32) -> Nat:
  match b:
    case True{}:
      0n
    case False{}:
      1n+U32.log2((n - 1 : U32))

def depth(+n: U32) -> Nat:
  depth.go(U32.is_le(n, 1), n)


# Keyed hashing, key derivation, extended output
# ----------------------------------------------
#
# BLAKE3's keyed and key-derivation modes hash the same tree from another
# starting key, with a mode flag on every compression: `key` is that key
# (the 32-byte key, or the context's derived key) and kf the flag
# (KEYED_HASH 16, DERIVE_KEY_CONTEXT 32, DERIVE_KEY_MATERIAL 64). The .k
# defs are the default mode's with the two threaded through; key = IV() and
# kf = 0 is the default mode.

def KEYED_HASH() -> U32:
  16

def DERIVE_KEY_CONTEXT() -> U32:
  32

def DERIVE_KEY_MATERIAL() -> U32:
  64

def chunk.go.k(n: Nat, r: Array<U32> & M16, +w: U32, cv: CV, +ctr: U32, +fl: U32,
  +endf: U32, +lastlen: U32, +kf: U32) -> Array<U32> & CV:
  match n:
    case 0n:
      (a, m) = r
      (a, compress(cv, m, ctr, 0, lastlen, ((fl .|. endf : U32) .|. kf : U32)))
    case 1n+p:
      (a, m) = r
      +w2 = (w + 16 : U32)
      chunk.go.k(p, ld(a, w2), w2, compress(cv, m, ctr, 0, 64, (fl .|. kf : U32)), ctr, 0,
        endf, lastlen, kf)

def chunk.k(a: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32,
  +rf: U32, +key: CV, +kf: U32) -> CV:
  +w = (c << 8n : U32)
  +m = (0 - Bool.to_u32(U32.is_eq((c + 1 : U32), nch)) : U32)
  +rem = ((last .&. m) .|. (1024 .&. U32.not(m)) : U32)
  +nb = U32.max(((rem + 63 : U32) >> 6n : U32), 1)
  +lastlen = (rem - ((nb - 1 : U32) << 6n : U32) : U32)
  chunk.fin(chunk.go.k(U32.to_nat((nb - 1 : U32)), ld(a, w), w, key,
    (cb + c : U32), CHUNK_START(), (CHUNK_END() .|. rf : U32), lastlen, kf))

def parent.k(l: CV, r: CV, +rf: U32, +key: CV, +kf: U32) -> CV:
  match l r:
    case CV{l0, l1, l2, l3, l4, l5, l6, l7} CV{r0, r1, r2, r3, r4, r5, r6, r7}:
      compress(key, M16{l0, l1, l2, l3, l4, l5, l6, l7, r0, r1, r2, r3, r4, r5, r6, r7}, 0, 0, 64, ((PARENT() .|. rf : U32) .|. kf : U32))

def tree1.k(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, b: Bool, aa: Array<U32> & Array<U32>, +c: U32, +n: U32,
  +cb: U32, +nch: U32, +last: U32, +rf: U32, +key: CV, +kf: U32) -> CV:
  match k b:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      chunk.k(a1, c, cb, nch, last, rf, key, kf)
    case 1n+p False{}:
      tree1.k(~dup, p, big(p, n), aa, c, n, cb, nch, last, rf, key, kf)
    case 1n+p True{}:
      (a1, a2) = aa
      +h = U32.shln(1, p)
      +n2 = (n - h : U32)
      l r = tree1.k(~dup, p, big(p, h), dup(a1), c, h, cb, nch, last, 0, key, kf) tree1.k(~dup, p, big(p, n2), dup(a2), (c + h : U32), n2, cb, nch, last, 0, key, kf)
      parent.k(l, r, rf, key, kf)

# The CV of a span (as hash.at) in any mode, on the scalar tree.
def hash.at.k(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32, +key: CV, +kf: U32) -> CV:
  +k = depth(nch)
  tree1.k(~dup, k, big(k, nch), dup(a), 0, nch, cb, nch, last, rf, key, kf)

# The root's node before its last compression: what the extended output
# expands, a block of 64 bytes for each counter (root.out).
type Root is Data:
  Root{cv: CV, m: M16, blen: U32, fl: U32}

def chunk.root.go(n: Nat, r: Array<U32> & M16, +w: U32, cv: CV, +ctr: U32, +fl: U32,
  +lastlen: U32, +kf: U32) -> Root:
  match n:
    case 0n:
      (a, m) = r
      _ = a
      Root{cv, m, lastlen, ((fl .|. CHUNK_END() : U32) .|. kf : U32)}
    case 1n+p:
      (a, m) = r
      +w2 = (w + 16 : U32)
      chunk.root.go(p, ld(a, w2), w2, compress(cv, m, ctr, 0, 64, (fl .|. kf : U32)), ctr, 0,
        lastlen, kf)

# The root of a one-chunk input (`last` bytes, counter cb): its last block.
def chunk.root(a: Array<U32>, +cb: U32, +last: U32, +key: CV, +kf: U32) -> Root:
  +nb = U32.max(((last + 63 : U32) >> 6n : U32), 1)
  +lastlen = (last - ((nb - 1 : U32) << 6n : U32) : U32)
  chunk.root.go(U32.to_nat((nb - 1 : U32)), ld(a, 0), 0, key, cb, CHUNK_START(), lastlen, kf)

# The root of a bigger input: the parent of its two children.
def parent.root(l: CV, r: CV, +key: CV, +kf: U32) -> Root:
  match l r:
    case CV{l0, l1, l2, l3, l4, l5, l6, l7} CV{r0, r1, r2, r3, r4, r5, r6, r7}:
      Root{key, M16{l0, l1, l2, l3, l4, l5, l6, l7, r0, r1, r2, r3, r4, r5, r6, r7}, 64, (PARENT() .|. kf : U32)}

# The whole compression: its first 8 words (as compress) and its last 8.
def out2(s: S16, c: CV) -> CV & CV:
  match s c:
    case S16{v0, v1, v2, v3, v4, v5, v6, v7, +v8, +v9, +v10, +v11, +v12, +v13, +v14, +v15} CV{h0, h1, h2, h3, h4, h5, h6, h7}:
      (CV{(v0 .^. v8 : U32), (v1 .^. v9 : U32), (v2 .^. v10 : U32), (v3 .^. v11 : U32), (v4 .^. v12 : U32), (v5 .^. v13 : U32), (v6 .^. v14 : U32), (v7 .^. v15 : U32)}, CV{(v8 .^. h0 : U32), (v9 .^. h1 : U32), (v10 .^. h2 : U32), (v11 .^. h3 : U32), (v12 .^. h4 : U32), (v13 .^. h5 : U32), (v14 .^. h6 : U32), (v15 .^. h7 : U32)})

def compress.xof(cv: CV, +m1: M16, +t0: U32, +t1: U32, +blen: U32, +flags: U32) -> CV & CV:
  match cv:
    case CV{+h0, +h1, +h2, +h3, +h4, +h5, +h6, +h7}:
      +m2 = perm(m1)
      +m3 = perm(m2)
      +m4 = perm(m3)
      +m5 = perm(m4)
      +m6 = perm(m5)
      +m7 = perm(m6)
      s0 = {S16{h0, h1, h2, h3, h4, h5, h6, h7, 1779033703, 3144134277, 1013904242, 2773480762, t0, t1, blen, flags} : S16}
      out2(round(round(round(round(round(round(round(s0, m1), m2), m3), m4), m5), m6), m7),
        CV{h0, h1, h2, h3, h4, h5, h6, h7})

# Block t (t1:t0) of the extended output: 64 bytes, as two CVs' words.
def root.out(r: Root, +t0: U32, +t1: U32) -> CV & CV:
  match r:
    case Root{cv, m, blen, fl}:
      compress.xof(cv, m, t0, t1, blen, (fl .|. ROOT() : U32))

@@WIDE@@
# Hex
# ---

def hex.pick(b: Bool, +d: U32) -> Char:
  match b:
    case True{}:
      Chr{(d + 48 : U32)}
    case False{}:
      Chr{(d + 87 : U32)}

def hex.digit(+d: U32) -> Char:
  hex.pick(U32.is_lt(d, 10), d)

def hex.byte(+x: U32, s: String) -> String:
  SCon{hex.digit(((x >> 4n) .&. 15 : U32)), SCon{hex.digit((x .&. 15 : U32)), s}}

def hex.word(+x: U32, s: String) -> String:
  hex.byte(x, hex.byte((x >> 8n : U32), hex.byte((x >> 16n : U32),
    hex.byte((x >> 24n : U32), s))))

# The 64 hex digits of a CV, in front of s.
def hex.onto(cv: CV, s: String) -> String:
  match cv:
    case CV{h0, h1, h2, h3, h4, h5, h6, h7}:
      hex.word(h0, hex.word(h1, hex.word(h2, hex.word(h3, hex.word(h4,
        hex.word(h5, hex.word(h6, hex.word(h7, s))))))))

def hex(cv: CV) -> String:
  hex.onto(cv, SNil{})
'''


# The entry points of the scalar module (--scalar): the fork tree of
# one-chunk leaves (tree1), with no 8-lane code. It is what JavaScript runs
# (the JS target is sequential, and its emitter overflows on compress8).
SCALAR = """
# Scalar entry points
# -------------------

# The bytes of the last chunk of a len-byte input of n chunks.
def tail(+len: U32, +n: U32) -> U32:
  (len - ((n - 1 : U32) << 10n : U32) : U32)

# The CV of a span: nch chunks counted from cb, the last holding `last`
# bytes; rf is ROOT for a whole input, 0 for a subtree.
def hash.at(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> CV:
  +k = depth(nch)
  tree1(~dup, k, big(k, nch), dup(a), 0, nch, cb, nch, last, rf)

# The BLAKE3 hash (first 32 bytes) of `len` bytes held in `a`.
def hash(~dup: Array<U32> -> Array<U32> & Array<U32>,
  a: Array<U32>, +len: U32) -> CV:
  +n = chunks(len)
  hash.at(~dup, a, 0, n, tail(len, n), ROOT())

"""


def main():
    scalar = "--scalar" in sys.argv
    m16 = ", ".join(f"m{i}: U32" for i in range(16))
    s16 = ", ".join(f"v{i}: U32" for i in range(16))
    iv = ", ".join(str(x) for x in IV)
    src = HEADER.format(m16=m16, s16=s16, iv=iv)
    src += gen_loader() + "\n"
    src += gen_round()
    src += AFTER_ROUND.format(
        mf=fields("m"),
        mf_plus=fields("m"),
        perm=", ".join(f"m{p}" for p in PERM),
        sf=fields("v"),
        cvout=", ".join(f"(v{i} .^. v{i + 8} : U32)" for i in range(8)),
        iv4=", ".join(str(x) for x in IV[:4]),
    )
    wide = WIDE.format(
        cv8=", ".join(f"h{l}_{i}: U32" for l, i in cv8_order()),
        b128=", ".join(f"m{l}_{i}: U32" for l, i in b128_order()),
        iv8=", ".join(str(IV[i]) for l, i in cv8_order()),
        ld8=gen_ld8(), compress8=gen_compress8(),
        compress8p=gen_compress8("compress8.p", parent=True), par8=gen_par8(),
        fold8=gen_fold8(),
        cv8f=cv8_fields("x"),
        **{f"c{l}": "CV{" + ", ".join(f"x{l}_{i}" for i in range(8)) + "}" for l in range(L)})
    if scalar:
        out = pathlib.Path(sys.argv[sys.argv.index("--scalar") + 1])
        src = src.replace("# BLAKE3 in Bend2", "# BLAKE3 in Bend2, scalar (gen_blake3.py --scalar)", 1)
        out.write_text(src + TREE.replace("@@WIDE@@", SCALAR))
        print(f"wrote {out}")
        return
    src += TREE.replace("@@WIDE@@", GPU_LEAVES + wide + gen_keyed8())
    OUT.write_text(src)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
