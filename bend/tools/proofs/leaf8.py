"""8-chunk leaves: leaf8.eq proves that where tree8 takes a Leaf8 (eight full
chunks on the 8-lane path), the result is tree1's scalar tree over those
chunks, for every array: leaf8 is fold8 over the group's lanes (gl.l*), and
tree1 unrolls to eight chunks, each full, at the same words and counters."""
from .common import L, CS, CE, TN, WL, FC, F8, wmatch

TS = "~share"


def t1(k, b, aa, c, n, rf):
    return f"B3.tree1({TS}, {k}n, {b}, {aa}, {c}, {n}, cb, nch, last, {rf})"


def paths(depth, c):
    """tree1's chunk indices under a node of the depth, as it computes them."""
    if depth == 0:
        return [c]
    h = 2 ** (depth - 1)
    return paths(depth - 1, c) + paths(depth - 1, f"({c} + {h} : U32)")


def parse(e):
    assert e.startswith("(") and e.endswith(" : U32)")
    body = e[1:-len(" : U32)")]
    i = body.rindex(" + ")
    return body[:i], int(body[i + 3:])


def norm(e, base="c"):
    """(j, proof of {e == (base + j)}) for a nested sum e; no proof when e is
    already (base + j), or base itself (j = 0)."""
    if e == base:
        return 0, None
    inner, k = parse(e)
    j, pf = norm(inner, base)
    if j == 0:
        return k, None
    assoc = f"A.u.add_assoc({base}, {j}, {k})"
    if pf is None:
        return j + k, assoc
    step = f"Equal.cong(U32, U32, z => (z + {k} : U32), {inner}, ({base} + {j} : U32), {pf})"
    return j + k, f"Equal.trans(U32, {e}, (({base} + {j} : U32) + {k} : U32), ({base} + {j + k} : U32), {step}, {assoc})"


P = paths(3, "c")
CHUNKS = [f"B3.chunk(x, {p}, cb, nch, last, 0)" for p in P]


def clone_and_chunk():
    lines, bi = wmatch("r", ["x", "y", "z"], "  ")
    full = FC("a", "(c << 8n : U32)", "(cb + c : U32)").replace(CE, f"({CE} .|. rf : U32)")
    return ('''
# A clone of a, with two live copies of a: what a tree node holds.
def CloneW(-a: Array<U32>) -> Type:
  Exists(Array<U32>, x => Exists(Array<U32>, y => {x == a : Array<U32>} & ({y == a : Array<U32>} & {Array.clone(U32, a) == (a, a) : Array<U32> & Array<U32>})))

''' + "def clone.w.h(-a: Array<U32>, r: Wits(a, 3n)) -> CloneW(a):\n" + "".join(lines) +
            f"{bi}(x, (y, (ex0, (ey0, tr(c => {{Array.clone(U32, c) == (c, c) : Array<U32> & Array<U32>}}, z, a, ez0, clone.dup(z))))))\n" + f'''
law clone.w:
  for a: Array<U32>
  CloneW(a)

def clone.w(a):
  clone.w.h(a, wits(2n, a))

# blake3.bend's chunk, with the bytes it holds (rem) and whether it is the
# last chunk (b) as parameters.
def chunk.r(a: Array<U32>, +c: U32, +cb: U32, +rf: U32, +rem: U32) -> B3.CV:
  +w = (c << 8n : U32)
  +nb = U32.max(((rem + 63 : U32) >> 6n : U32), 1)
  +lastlen = (rem - ((nb - 1 : U32) << 6n : U32) : U32)
  B3.chunk.fin(B3.chunk.go(U32.to_nat((nb - 1 : U32)), B3.ld(a, w), w, B3.IV(),
    (cb + c : U32), {CS}, ({CE} .|. rf : U32), lastlen))

def chunk.b(a: Array<U32>, +c: U32, +cb: U32, +last: U32, +rf: U32, b: Bool) -> B3.CV:
  +m = (0 - Bool.to_u32(b) : U32)
  chunk.r(a, c, cb, rf, ((last .&. m) .|. (1024 .&. U32.not(m)) : U32))

law chunk.split:
  for -a: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {{B3.chunk(a, c, cb, nch, last, rf) == chunk.b(a, c, cb, last, rf, U32.is_eq((c + 1 : U32), nch)) : B3.CV}}

def chunk.split(a, c, cb, nch, last, rf):
  {{==}}

# A chunk that is not the last holds 1024 bytes, whatever last is.
law chunk.full:
  for -a: Array<U32>
  for +c: U32
  for +cb: U32
  for +last: U32
  for +rf: U32
  {{chunk.b(a, c, cb, last, rf, False{{}}) == {full} : B3.CV}}

def chunk.full(a, c, cb, last, rf):
  %Equal.sym(U32, (last .&. 0 : U32), 0, A.u.and_zero(last)) :
    {{chunk.r(a, c, cb, rf, (_ .|. (1024 .&. U32.not(0) : U32) : U32)) == {full} : B3.CV}}
  {{==}}

# The last chunk, when it holds 1024 bytes.
law chunk.last:
  for -a: Array<U32>
  for +c: U32
  for +cb: U32
  for +rf: U32
  {{chunk.b(a, c, cb, 1024, rf, True{{}}) == {full} : B3.CV}}

def chunk.last(a, c, cb, rf):
  {{==}}
''')


def lanes():
    G = lambda arr: f"Pair.snd(Array<U32>, B3.CV8, B3.group({arr}, c, t))"
    out = [f'''
law leaf8.fin.snd:
  for r: Array<U32> & B3.CV8
  for +rf: U32
  {{B3.leaf8.fin(r, rf) == B3.fold8(Pair.snd(Array<U32>, B3.CV8, r), rf) : B3.CV}}

def leaf8.fin.snd(r, rf):
  match r:
    case (a, x):
      {{==}}

law fold8.lanes:
  for +x: B3.CV8
  for +rf: U32
  {{B3.fold8(x, rf) == {F8([f"cv.at(L{l}{{}}, x)" for l in range(L)], "rf")} : B3.CV}}

def fold8.lanes(x, rf):
  match x:
    case B3.CV8{{{", ".join(f"h{l}_{i}" for i in range(8) for l in range(L))}}}:
      {{==}}
''']
    names = ["x0", "x1"] + [f"z{l}" for l in range(L)]
    lines, bi = wmatch("r", names, "  ")
    fcs = [FC("a", WL(l, "(c << 8n : U32)"), f"(t + {l} : U32)") for l in range(L)]
    goal = f"{{B3.leaf8(a, c, t, rf) == {F8(fcs, 'rf')} : B3.CV}}"
    b = [f"{bi}%Equal.sym(B3.CV, B3.leaf8.fin(B3.group(a, c, t), rf), B3.fold8({G('a')}, rf), "
         f"tr(arr => {{B3.leaf8.fin(B3.group(arr, c, t), rf) == B3.fold8({G('arr')}, rf) : B3.CV}}, x0, a, ex00, leaf8.fin.snd(B3.group(x0, c, t), rf))) :\n"
         f"{bi}  {{_ == {F8(fcs, 'rf')} : B3.CV}}\n"]
    lanes_a = [f"cv.at(L{l}{{}}, {G('a')})" for l in range(L)]
    b.append(f"{bi}%Equal.sym(B3.CV, B3.fold8({G('a')}, rf), {F8(lanes_a, 'rf')}, "
             f"tr(arr => {{B3.fold8({G('arr')}, rf) == {F8([f'cv.at(L{l}{{}}, ' + G('arr') + ')' for l in range(L)], 'rf')} : B3.CV}}, "
             f"x1, a, ex10, fold8.lanes({G('x1')}, rf))) :\n"
             f"{bi}  {{_ == {F8(fcs, 'rf')} : B3.CV}}\n")
    cur = list(lanes_a)
    for l in range(L):
        hole = list(cur)
        hole[l] = "_"
        fact = (f"tr(arr => {{cv.at(L{l}{{}}, {G('arr')}) == {FC('arr', WL(l, '(c << 8n : U32)'), f'(t + {l} : U32)')} : B3.CV}}, "
                f"z{l}, a, ez{l}0, gl.l{l}(z{l}, c, t))")
        b.append(f"{bi}%Equal.sym(B3.CV, {lanes_a[l]}, {fcs[l]}, {fact}) :\n{bi}  {{{F8(hole, 'rf')} == {F8(fcs, 'rf')} : B3.CV}}\n")
        cur[l] = fcs[l]
    b.append(f"{bi}{{==}}\n")
    out.append(f"\ndef leaf8.lanes.h(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, r: Wits(a, {len(names)}n)) -> {goal}:\n" +
               "".join(lines) + "".join(b))
    out.append(f'''
# 8 full chunks on the 8-lane path are their scalar chains under fold8's
# parents, for every array.
law leaf8.lanes:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {goal}

def leaf8.lanes(a, c, t, rf):
  leaf8.lanes.h(a, c, t, rf, wits({len(names) - 1}n, a))
''')
    return "".join(out)


def tree1_d3():
    R = F8(CHUNKS, "rf")
    lv1 = f"B3.parent({t1(2, 'True{}', '_', 'c', 4, 0)}, {t1(2, 'True{}', '_', '(c + 4 : U32)', 4, 0)}, rf)"
    d2 = ["c", "(c + 2 : U32)", "(c + 4 : U32)", "((c + 4 : U32) + 2 : U32)"]
    lv2 = (f"B3.parent(B3.parent({t1(1, 'True{}', '_', d2[0], 2, 0)}, {t1(1, 'True{}', '_', d2[1], 2, 0)}, 0), "
           f"B3.parent({t1(1, 'True{}', '_', d2[2], 2, 0)}, {t1(1, 'True{}', '_', d2[3], 2, 0)}, 0), rf)")
    lv3 = F8([t1(0, 'False{}', '_', p, 1, 0) for p in P], "rf")
    clone = lambda z: f"tr(arr => {{Array.clone(U32, arr) == (arr, arr) : Array<U32> & Array<U32>}}, {z}, x, e{z}0, clone.dup({z}))"
    lines, bi = wmatch("r", ["z1", "z2", "z3"], "  ")
    body = [f"{bi}%Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, x), (x, x), {clone(z)}) :\n{bi}  {{{lv} == {R} : B3.CV}}\n"
            for lv, z in ((lv1, "z1"), (lv2, "z2"), (lv3, "z3"))]
    body.append(f"{bi}{{==}}\n")
    goal = f"{{{t1(3, 'True{}', '(x, x)', 'c', 8, 'rf')} == {R} : B3.CV}}"
    return (f"\ndef tree1.d3.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, r: Wits(x, 3n)) -> {goal}:\n" +
            "".join(lines) + "".join(body) + f'''
# tree1 over 8 chunks from c is the 8 chunk CVs under 7 parents.
law tree1.d3:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {goal}

def tree1.d3(x, c, cb, nch, last, rf):
  tree1.d3.h(x, c, cb, nch, last, rf, wits(2n, x))
''')


def idx_fact(i, p):
    """{(p << 8n) == WL(i, (c << 8n))}: tree1's word offset is the lane's."""
    if i == 0:
        return None
    j, pf = norm(p)
    assert j == i
    sh = f"A.u.shln_add(c, {i}, 8n)"
    if pf is None:
        return sh
    return (f"Equal.trans(U32, ({p} << 8n : U32), ((c + {i} : U32) << 8n : U32), {WL(i, '(c << 8n : U32)')}, "
            f"Equal.cong(U32, U32, z => (z << 8n : U32), {p}, (c + {i} : U32), {pf}), {sh})")


def ctr_fact(i, p):
    """{(cb + p) == ((cb + c) + i)}: tree1's counter is the lane's."""
    if i == 0:
        return "Equal.sym(U32, ((cb + c : U32) + 0 : U32), (cb + c : U32), A.u.add_zero_r((cb + c : U32)))"
    j, pf = norm(p)
    back = f"Equal.sym(U32, ((cb + c : U32) + {i} : U32), (cb + (c + {i} : U32) : U32), A.u.add_assoc(cb, c, {i}))"
    if pf is None:
        return back
    return (f"Equal.trans(U32, (cb + {p} : U32), (cb + (c + {i} : U32) : U32), ((cb + c : U32) + {i} : U32), "
            f"Equal.cong(U32, U32, z => (cb + z : U32), {p}, (c + {i} : U32), {pf}), {back})")


def chunk_eqs():
    FCp = lambda w, t: FC("x", w, t).replace(CE, f"({CE} .|. 0 : U32)")
    out = []
    for i, p in enumerate(P):
        rhs = FC("x", WL(i, "(c << 8n : U32)"), f"((cb + c : U32) + {i} : U32)")
        last = i == L - 1
        if last:
            head_extra = ("  for b: Bool\n  for +eb: {U32.is_eq((" + p + " + 1 : U32), nch) == b : Bool}\n"
                          "  for +el: {Bool.or(Bool.not(b), U32.is_eq(last, 1024)) == True{} : Bool}\n")
            sig_extra = ", b, eb, el"
        else:
            head_extra = "  for +e: {U32.is_eq((" + p + " + 1 : U32), nch) == False{} : Bool}\n"
            sig_extra = ", e"
        idx = idx_fact(i, p)
        tail = []
        if idx:
            tail.append(f"%Equal.sym(U32, ({p} << 8n : U32), {WL(i, '(c << 8n : U32)')}, {idx}) :\n"
                        f"    {{{FCp('_', f'(cb + {p} : U32)')} == {rhs} : B3.CV}}\n")
        w_now = WL(i, '(c << 8n : U32)') if idx else f"({p} << 8n : U32)"
        tail.append(f"%Equal.sym(U32, (cb + {p} : U32), ((cb + c : U32) + {i} : U32), {ctr_fact(i, p)}) :\n"
                    f"    {{{FCp(w_now, '_')} == {rhs} : B3.CV}}\n")
        tail.append("{==}\n")
        full_rw = (f"%Equal.sym(B3.CV, chunk.b(x, {p}, cb, last, 0, False{{}}), {FCp(f'({p} << 8n : U32)', f'(cb + {p} : U32)')}, "
                   f"chunk.full(x, {p}, cb, last, 0)) :\n    {{_ == {rhs} : B3.CV}}\n")
        if not last:
            body = (f"  %Equal.sym(Bool, U32.is_eq(({p} + 1 : U32), nch), False{{}}, e) :\n    {{chunk.b(x, {p}, cb, last, 0, _) == {rhs} : B3.CV}}\n"
                    + "  " + full_rw + "".join("  " + t for t in tail))
        else:
            ind = "      "
            sub = lambda t: ind + t.replace("\n    ", f"\n{ind}  ")
            bf = (f"{ind}%Equal.sym(Bool, U32.is_eq(({p} + 1 : U32), nch), False{{}}, eb) :\n{ind}  {{chunk.b(x, {p}, cb, last, 0, _) == {rhs} : B3.CV}}\n"
                  + sub(full_rw) + "".join(sub(t) for t in tail))
            last_rw = (f"{ind}%Equal.sym(Bool, U32.is_eq(({p} + 1 : U32), nch), True{{}}, eb) :\n{ind}  {{chunk.b(x, {p}, cb, last, 0, _) == {rhs} : B3.CV}}\n"
                       f"{ind}%Equal.sym(U32, last, 1024, A.u.eq_sound(last, 1024, el)) :\n{ind}  {{chunk.b(x, {p}, cb, _, 0, True{{}}) == {rhs} : B3.CV}}\n"
                       f"{ind}%Equal.sym(B3.CV, chunk.b(x, {p}, cb, 1024, 0, True{{}}), {FCp(f'({p} << 8n : U32)', f'(cb + {p} : U32)')}, chunk.last(x, {p}, cb, 0)) :\n"
                       f"{ind}  {{_ == {rhs} : B3.CV}}\n" + "".join(sub(t) for t in tail))
            body = f"  match b:\n    case False{{}}:\n{bf}    case True{{}}:\n{last_rw}"
        out.append(f'''
law chunk.eq{i}:
  for -x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
{head_extra}  {{{CHUNKS[i]} == {rhs} : B3.CV}}

def chunk.eq{i}(x, c, cb, nch, last{sig_extra}):
{body}''')
    return "".join(out)


def fullness():
    return f'''
law full.lt:
  for +e: U32
  for +nch: U32
  for +last: U32
  for +en: {{e == nch : U32}}
  for +eb: {{U32.is_eq(e, nch) == True{{}} : Bool}}
  {{B3.full(e, nch, last) == (U32.is_lt(e, e) || (True{{}} && U32.is_eq(last, 1024))) : Bool}}

def full.lt(e, nch, last, en, eb):
  %Equal.sym(Bool, U32.is_eq(e, nch), True{{}}, eb) :
    {{(U32.is_lt(e, nch) || (_ && U32.is_eq(last, 1024))) == (U32.is_lt(e, e) || (True{{}} && U32.is_eq(last, 1024))) : Bool}}
  %en : {{(U32.is_lt(e, _) || (True{{}} && U32.is_eq(last, 1024))) == (U32.is_lt(e, e) || (True{{}} && U32.is_eq(last, 1024))) : Bool}}
  {{==}}

law full.drop:
  for +e: U32
  for +last: U32
  {{(U32.is_lt(e, e) || (True{{}} && U32.is_eq(last, 1024))) == U32.is_eq(last, 1024) : Bool}}

def full.drop(e, last):
  %Equal.sym(Bool, U32.is_lt(e, e), False{{}}, A.u.lt_self(e)) :
    {{(_ || (True{{}} && U32.is_eq(last, 1024))) == U32.is_eq(last, 1024) : Bool}}
  {{==}}

# Chunk c + j of n chunks from c (j < n) is not the last of nch when c + n <= nch.
law nonlast:
  for +c: U32
  for +nch: U32
  for +j: U32
  for +n: Nat
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, n), {TN("nch")}) == True{{}} : Bool}}
  for +ej: {{Nat.is_lt({TN("j")}, n) == True{{}} : Bool}}
  {{U32.is_eq((c + j : U32), nch) == False{{}} : Bool}}

def nonlast(c, nch, j, n, inv, ej):
  +cj = Nat.add({TN("c")}, {TN("j")})
  +cn = Nat.add({TN("c")}, n)
  +lt = A.n.lt_le(cj, cn, {TN("nch")}, A.n.add_lt({TN("c")}, {TN("j")}, n, ej), inv)
  +le = A.n.le_trans(cj, cn, {TN("nch")}, A.n.add_le({TN("c")}, {TN("j")}, n, A.n.lt_to_le({TN("j")}, n, ej)), inv)
  %Equal.sym(Bool, U32.is_eq((c + j : U32), nch), Nat.is_eq({TN("(c + j : U32)")}, {TN("nch")}), A.u.is_eq_nat((c + j : U32), nch)) : {{_ == False{{}} : Bool}}
  %Equal.sym(Nat, {TN("(c + j : U32)")}, cj, A.u.tn_add(c, j, nch, le)) : {{Nat.is_eq(_, {TN("nch")}) == False{{}} : Bool}}
  A.n.lt_ne(cj, {TN("nch")}, lt)

# The last chunk of a full span holds 1024 bytes.
law full.last.b:
  for +e: U32
  for +nch: U32
  for +last: U32
  for b: Bool
  for +eb: {{U32.is_eq(e, nch) == b : Bool}}
  for +ef: {{B3.full(e, nch, last) == True{{}} : Bool}}
  {{Bool.or(Bool.not(b), U32.is_eq(last, 1024)) == True{{}} : Bool}}

def full.last.b(e, nch, last, b, eb, ef):
  match b:
    case False{{}}:
      {{==}}
    case True{{}}:
      +en = A.u.eq_sound(e, nch, eb)
      +x = Equal.trans(Bool, B3.full(e, nch, last), (U32.is_lt(e, e) || (True{{}} && U32.is_eq(last, 1024))), U32.is_eq(last, 1024),
        full.lt(e, nch, last, en, eb),
        full.drop(e, last))
      Equal.trans(Bool, U32.is_eq(last, 1024), B3.full(e, nch, last), True{{}}, Equal.sym(Bool, B3.full(e, nch, last), U32.is_eq(last, 1024), x), ef)
'''


def leaf8_eq():
    inv8 = f"{{Nat.is_le(Nat.add({TN('c')}, 8n), {TN('nch')}) == True{{}} : Bool}}"
    ef8 = "{B3.full((c + 8 : U32), nch, last) == True{} : Bool}"
    L8 = "B3.leaf8(x, c, (cb + c : U32), rf)"
    T3 = t1(3, "True{}", "(x, x)", "c", 8, "rf")
    fcs = [FC("x", WL(l, "(c << 8n : U32)"), f"((cb + c : U32) + {l} : U32)") for l in range(L)]
    facts = []
    for i, p in enumerate(P[:-1]):
        e = f"({p} + 1 : U32)"
        j, pf = norm(e)
        assert j == i + 1
        nl = f"nonlast(c, nch, {j}, 8n, inv, {{==}})"
        facts.append(nl if pf is None else
                     f"Equal.trans(Bool, U32.is_eq({e}, nch), U32.is_eq((c + {j} : U32), nch), False{{}}, "
                     f"Equal.cong(U32, Bool, z => U32.is_eq(z, nch), {e}, (c + {j} : U32), {pf}), {nl})")
    e7 = f"({P[-1]} + 1 : U32)"
    j7, pf7 = norm(e7)
    assert j7 == 8
    eb7 = f"Equal.cong(U32, Bool, z => U32.is_eq(z, nch), {e7}, (c + 8 : U32), {pf7})"
    el7 = "full.last.b((c + 8 : U32), nch, last, U32.is_eq((c + 8 : U32), nch), {==}, ef)"
    ceqs = [f"chunk.eq{i}(x, c, cb, nch, last, {facts[i]})" for i in range(L - 1)]
    ceqs.append(f"chunk.eq7(x, c, cb, nch, last, U32.is_eq((c + 8 : U32), nch), {eb7}, {el7})")
    Lf = (f"tr(arr => {{B3.leaf8(arr, c, (cb + c : U32), rf) == "
          f"{F8([FC('arr', WL(l, '(c << 8n : U32)'), f'((cb + c : U32) + {l} : U32)') for l in range(L)], 'rf')} : B3.CV}}, "
          f"x1, x, e1, leaf8.lanes(x1, c, (cb + c : U32), rf))")
    Rf = (f"tr(arr => {{{t1(3, 'True{}', '(arr, arr)', 'c', 8, 'rf')} == {F8([f'B3.chunk(arr, {p}, cb, nch, last, 0)' for p in P], 'rf')} : B3.CV}}, "
          f"x2, x, e2, tree1.d3(x2, c, cb, nch, last, rf))")
    body = [f"  %Equal.sym(B3.CV, {L8}, {F8(fcs, 'rf')}, {Lf}) :\n    {{_ == {T3} : B3.CV}}\n",
            f"  %Equal.sym(B3.CV, {T3}, {F8(CHUNKS, 'rf')}, {Rf}) :\n    {{{F8(fcs, 'rf')} == _ : B3.CV}}\n"]
    cur = list(CHUNKS)
    for i in range(L):
        hole = list(cur)
        hole[i] = "_"
        body.append(f"  %Equal.sym(B3.CV, {CHUNKS[i]}, {fcs[i]}, {ceqs[i]}) :\n    {{{F8(fcs, 'rf')} == {F8(hole, 'rf')} : B3.CV}}\n")
        cur[i] = fcs[i]
    body.append("  {==}\n")
    return f'''
# A full 8-chunk node: the CPU's 8-lane leaf is the scalar tree over its
# chunks, for every array and every span that holds it whole.
law leaf8.eq:
  for -x: Array<U32>
  for x1: Array<U32>
  for +e1: {{x1 == x : Array<U32>}}
  for x2: Array<U32>
  for +e2: {{x2 == x : Array<U32>}}
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +inv: {inv8}
  for +ef: {ef8}
  {{{L8} == {T3} : B3.CV}}

def leaf8.eq(x, x1, e1, x2, e2, c, cb, nch, last, rf, inv, ef):
''' + "".join(body)


def text():
    return clone_and_chunk() + lanes() + tree1_d3() + chunk_eqs() + fullness() + leaf8_eq()
