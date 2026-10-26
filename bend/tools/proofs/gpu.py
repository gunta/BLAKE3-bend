"""The GPU tree: treeg's leaves (g4, g16, g64: chains of four under parents,
gch at the bottom; quad and qtree for strided lanes) are tree1's scalar
subtrees, and treeg is tree1 node for node, for every input."""
from .common import CS, CE, TN, WL, FC, wmatch
from .leaf8 import t1, paths, norm, idx_fact, ctr_fact

# A level of the GPU's flat leaves: (name, sub-leaf, chunks a sub-leaf spans).
LEVELS = [("g4", "gch", 1), ("g16", "g4", 4), ("g64", "g16", 16)]
DEPTH = {"gch": 0, "g4": 2, "g16": 4, "g64": 6}


def sndc(r):
    return f"Pair.snd(Array<U32>, B3.CV, {r})"


def scalar_loop():
    w16 = "(w + 16 : U32)"
    go = lambda n, r: f"B3.chunk.go({n}, {r}, w, cv, ctr, fl, endf, lastlen)"
    return f'''
# The scalar loader and chunk loop hand their array back.
law ld.fst:
  for a: Array<U32>
  for +w: U32
  {{Pair.fst(Array<U32>, B3.M16, B3.ld(a, w)) == a : Array<U32>}}

def ld.fst(a, w):
  Equal.cong(Array<U32> & B3.M16, Array<U32>, p => Pair.fst(Array<U32>, B3.M16, p), B3.ld(a, w), (a, Pair.snd(Array<U32>, B3.M16, B3.ld(a, w))), ld.eta(a, w))

law cg.eta:
  for +n: Nat
  for -a0: Array<U32>
  for r: Array<U32> & B3.M16
  for +er: {{Pair.fst(Array<U32>, B3.M16, r) == a0 : Array<U32>}}
  for +w: U32
  for +cv: B3.CV
  for +ctr: U32
  for +fl: U32
  for +endf: U32
  for +lastlen: U32
  for bun: Bun1(a0, n)
  {{{go("n", "r")} == (a0, {sndc(go("n", "r"))}) : Array<U32> & B3.CV}}

def cg.eta(n, a0, r, er, w, cv, ctr, fl, endf, lastlen, bun):
  match n:
    case 0n:
      match r:
        case (a, +m):
          _ = bun
          %er : {{(a, B3.compress(cv, m, ctr, 0, lastlen, (fl .|. endf : U32))) == (_, B3.compress(cv, m, ctr, 0, lastlen, (fl .|. endf : U32))) : Array<U32> & B3.CV}}
          {{==}}
    case 1n+q:
      match r:
        case (a, +m):
          match bun:
            case (lvl, rest):
              match lvl:
                case (x1, l1):
                  match l1:
                    case (+e1, l1b):
                      _ = l1b
                      +f = eq.trans(Pair.fst(Array<U32>, B3.M16, B3.ld(a, {w16})), a, a0, tr(arr => {{Pair.fst(Array<U32>, B3.M16, B3.ld(arr, {w16})) == arr : Array<U32>}}, x1, a,
                        eq.trans(x1, a0, a, e1, Equal.sym(Array<U32>, a, a0, er)), ld.fst(x1, {w16})), er)
                      cg.eta(q, a0, B3.ld(a, {w16}), f, {w16}, B3.compress(cv, m, ctr, 0, 64, fl), ctr, 0, endf, lastlen, rest)

# The CV of a pair, by its fin or by snd.
law fin.snd:
  for r: Array<U32> & B3.CV
  {{Pair.snd(Array<U32>, B3.CV, r) == B3.chunk.fin(r) : B3.CV}}

def fin.snd(r):
  match r:
    case (a, x):
      {{==}}

law gfin.snd:
  for r: Array<U32> & B3.CV
  {{B3.g.fin(r) == Pair.snd(Array<U32>, B3.CV, r) : B3.CV}}

def gfin.snd(r):
  match r:
    case (a, x):
      {{==}}
'''


def gch():
    W = "(c << 8n : U32)"
    cgo = lambda arr: f"B3.chunk.go(15n, B3.ld({arr}, {W}), {W}, B3.IV(), t, {CS}, {CE}, 64)"
    goal = f"{{B3.gch(a, c, t, rf) == (a, {sndc('B3.gch(a, c, t, rf)')}) : Array<U32> & B3.CV}}"
    lines, bi = wmatch("r", ["x1", "x2"], "  ")
    lines = [ln.replace("(+ex10, ", "(+ex1o, ").replace("(+ex20, ", "(+ex2o, ") for ln in lines]
    body = (f"{bi}+ex1 = eq.trans(x1, s, a, ex1o, es)\n{bi}+ex2 = eq.trans(x2, s, a, ex2o, es)\n"
            f"{bi}+f = eq.trans(Pair.fst(Array<U32>, B3.M16, B3.ld(x1, {W})), x1, a, tr(arr => {{Pair.fst(Array<U32>, B3.M16, B3.ld(arr, {W})) == arr : Array<U32>}}, "
            f"x2, x1, eq.trans(x2, a, x1, ex2, Equal.sym(Array<U32>, x1, a, ex1)), ld.fst(x2, {W})), ex1)\n"
            f"{bi}tr(arr => {{{cgo('arr')} == (a, {sndc(cgo('arr'))}) : Array<U32> & B3.CV}}, x1, a, ex1,\n"
            f"{bi}  cg.eta(15n, a, B3.ld(x1, {W}), f, {W}, B3.IV(), t, {CS}, {CE}, 64, bb))\n")
    return (f"\ndef gch.eta.h2(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, -s: Array<U32>, +es: {{s == a : Array<U32>}}, "
            f"r: Wits(s, 2n), bb: Bun1(a, 15n)) -> {goal}:\n" + "".join(lines) + body + f'''
def gch.eta.h1(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, r: BunS1(a, 15n)) -> {goal}:
  match r:
    case (s, r2):
      match r2:
        case (+es, bb):
          gch.eta.h2(a, c, t, rf, s, es, wits(1n, s), bb)

# A GPU lane's chunk hands its array back...
law gch.eta:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {goal}

def gch.eta(a, c, t, rf):
  gch.eta.h1(a, c, t, rf, bun1(15n, a))

# ...and its CV is the full chunk's.
law gch.fc:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {{{sndc('B3.gch(a, c, t, rf)')} == {FC('a', W, 't')} : B3.CV}}

def gch.fc(a, c, t, rf):
  fin.snd(B3.gch(a, c, t, rf))
''')


def chain(name, sub, s):
    """name(a, c, t, rf): four sub-leaves s chunks apart under three parents.
    name.eta: it hands its array back; name.val: its CV."""
    cs = ["c"] + [f"(c + {s * i} : U32)" for i in range(1, 4)]
    ts = ["t"] + [f"(t + {s * i} : U32)" for i in range(1, 4)]
    S = lambda arr, i: sndc(f"B3.{sub}({arr}, {cs[i]}, {ts[i]}, 0)")
    Ss = [S("a", i) for i in range(4)]
    states = [f"B3.{name}.s0(_, c, t, rf)",
              f"B3.{name}.s1(_, c, t, {Ss[0]}, rf)",
              f"B3.{name}.s2(_, c, t, B3.parent({Ss[0]}, {Ss[1]}, 0), rf)",
              f"B3.{name}.s3(_, B3.parent({Ss[0]}, {Ss[1]}, 0), {Ss[2]}, rf)"]
    val = f"B3.parent(B3.parent({Ss[0]}, {Ss[1]}, 0), B3.parent({Ss[2]}, {Ss[3]}, 0), rf)"
    fact = lambda i, z: (f"tr(arr => {{B3.{sub}(arr, {cs[i]}, {ts[i]}, 0) == (arr, {S('arr', i)}) : Array<U32> & B3.CV}}, "
                         f"{z}, a, e{z}0, {sub}.eta({z}, {cs[i]}, {ts[i]}, 0))")
    rew = lambda i, z, motive: (f"%Equal.sym(Array<U32> & B3.CV, B3.{sub}(a, {cs[i]}, {ts[i]}, 0), (a, {Ss[i]}), {fact(i, z)}) :\n"
                                f"    {motive}\n")
    out = []
    # eta: rewrite both sides' chains, one sub-leaf at a time
    lines, bi = wmatch("r", ["z0", "z1", "z2", "z3"], "  ")
    b = []
    for i in range(4):
        st = states[i]
        b.append(bi + rew(i, f"z{i}", f"{{{st} == (a, {sndc(st)}) : Array<U32> & B3.CV}}").replace("\n    ", f"\n{bi}  "))
    b.append(f"{bi}{{==}}\n")
    goal_eta = f"{{B3.{name}(a, c, t, rf) == (a, {sndc(f'B3.{name}(a, c, t, rf)')}) : Array<U32> & B3.CV}}"
    out.append(f"\ndef {name}.eta.h(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, r: Wits(a, 4n)) -> {goal_eta}:\n" +
               "".join(lines) + "".join(b) + f'''
law {name}.eta:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {goal_eta}

def {name}.eta(a, c, t, rf):
  {name}.eta.h(a, c, t, rf, wits(3n, a))
''')
    lines, bi = wmatch("r", ["z0", "z1", "z2", "z3"], "  ")
    b = []
    for i in range(4):
        b.append(bi + rew(i, f"z{i}", f"{{{sndc(states[i])} == {val} : B3.CV}}").replace("\n    ", f"\n{bi}  "))
    b.append(f"{bi}{{==}}\n")
    goal_val = f"{{{sndc(f'B3.{name}(a, c, t, rf)')} == {val} : B3.CV}}"
    out.append(f"\ndef {name}.val.h(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, r: Wits(a, 4n)) -> {goal_val}:\n" +
               "".join(lines) + "".join(b) + f'''
# {name}: four {sub}s, {s} chunk{"s" if s > 1 else ""} apart, under three parents.
law {name}.val:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {goal_val}

def {name}.val(a, c, t, rf):
  {name}.val.h(a, c, t, rf, wits(3n, a))
''')
    return "".join(out)


def tree1_unroll(d):
    """tree1 over 4^(d/2 + 1) full chunks from c: its four quarters, two
    levels of clone rewrites."""
    q = 4 ** (d // 2)          # chunks a quarter spans
    k = d + 2
    c2 = ["c", f"(c + {2 * q} : U32)"]
    c4 = ["c", f"(c + {q} : U32)", f"(c + {2 * q} : U32)", f"((c + {2 * q} : U32) + {q} : U32)"]
    T = lambda c: t1(d, "True{}" if d > 0 else "False{}", "(x, x)", c, q, "0")
    R = f"B3.parent(B3.parent({T(c4[0])}, {T(c4[1])}, 0), B3.parent({T(c4[2])}, {T(c4[3])}, 0), rf)"
    lv1 = f"B3.parent({t1(k - 1, 'True{}', '_', c2[0], 2 * q, 0)}, {t1(k - 1, 'True{}', '_', c2[1], 2 * q, 0)}, rf)"
    T_ = lambda c: t1(d, "True{}" if d > 0 else "False{}", "_", c, q, "0")
    lv2 = f"B3.parent(B3.parent({T_(c4[0])}, {T_(c4[1])}, 0), B3.parent({T_(c4[2])}, {T_(c4[3])}, 0), rf)"
    clone = lambda z: f"tr(arr => {{Array.clone(U32, arr) == (arr, arr) : Array<U32> & Array<U32>}}, {z}, x, e{z}0, clone.dup({z}))"
    lines, bi = wmatch("r", ["z1", "z2"], "  ")
    body = [f"{bi}%Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, x), (x, x), {clone(z)}) :\n{bi}  {{{lv} == {R} : B3.CV}}\n"
            for lv, z in ((lv1, "z1"), (lv2, "z2"))]
    body.append(f"{bi}{{==}}\n")
    Tk = t1(k, "True{}", "(x, x)", "c", 4 * q, "rf")
    goal = f"{{{Tk} == {R} : B3.CV}}"
    return (f"\ndef tree1.u{k}.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, r: Wits(x, 2n)) -> {goal}:\n" +
            "".join(lines) + "".join(body) + f'''
# tree1 over {4 * q} chunks from c is its four quarters under 3 parents.
law tree1.u{k}:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {goal}

def tree1.u{k}(x, c, cb, nch, last, rf):
  tree1.u{k}.h(x, c, cb, nch, last, rf, wits(1n, x))
''')


def chunk_last(i, p, name):
    """chunk name: chunk i of a leaf (path p) is its full chain, also when it
    is the span's last chunk (then it holds 1024 bytes)."""
    FCp = lambda w, t: FC("x", w, t).replace(CE, f"({CE} .|. 0 : U32)")
    rhs = FC("x", WL(i, "(c << 8n : U32)"), f"((cb + c : U32) + {i} : U32)")
    idx = idx_fact(i, p)
    ind = "      "
    tail = []
    if idx:
        tail.append(f"{ind}%Equal.sym(U32, ({p} << 8n : U32), {WL(i, '(c << 8n : U32)')}, {idx}) :\n"
                    f"{ind}  {{{FCp('_', f'(cb + {p} : U32)')} == {rhs} : B3.CV}}\n")
    w_now = WL(i, '(c << 8n : U32)') if idx else f"({p} << 8n : U32)"
    tail.append(f"{ind}%Equal.sym(U32, (cb + {p} : U32), ((cb + c : U32) + {i} : U32), {ctr_fact(i, p)}) :\n"
                f"{ind}  {{{FCp(w_now, '_')} == {rhs} : B3.CV}}\n")
    tail.append(f"{ind}{{==}}\n")
    full = (f"{ind}%Equal.sym(B3.CV, chunk.b(x, {p}, cb, last, 0, False{{}}), {FCp(f'({p} << 8n : U32)', f'(cb + {p} : U32)')}, "
            f"chunk.full(x, {p}, cb, last, 0)) :\n{ind}  {{_ == {rhs} : B3.CV}}\n")
    last = (f"{ind}%Equal.sym(B3.CV, chunk.b(x, {p}, cb, 1024, 0, True{{}}), {FCp(f'({p} << 8n : U32)', f'(cb + {p} : U32)')}, "
            f"chunk.last(x, {p}, cb, 0)) :\n{ind}  {{_ == {rhs} : B3.CV}}\n")
    return f'''
law {name}:
  for -x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for b: Bool
  for +eb: {{U32.is_eq(({p} + 1 : U32), nch) == b : Bool}}
  for +el: {{Bool.or(Bool.not(b), U32.is_eq(last, 1024)) == True{{}} : Bool}}
  {{B3.chunk(x, {p}, cb, nch, last, 0) == {rhs} : B3.CV}}

def {name}(x, c, cb, nch, last, b, eb, el):
  match b:
    case False{{}}:
{ind}%Equal.sym(Bool, U32.is_eq(({p} + 1 : U32), nch), False{{}}, eb) :
{ind}  {{chunk.b(x, {p}, cb, last, 0, _) == {rhs} : B3.CV}}
''' + full + "".join(tail) + f'''    case True{{}}:
{ind}%Equal.sym(Bool, U32.is_eq(({p} + 1 : U32), nch), True{{}}, eb) :
{ind}  {{chunk.b(x, {p}, cb, last, 0, _) == {rhs} : B3.CV}}
{ind}%Equal.sym(U32, last, 1024, A.u.eq_sound(last, 1024, el)) :
{ind}  {{chunk.b(x, {p}, cb, _, 0, True{{}}) == {rhs} : B3.CV}}
''' + last + "".join(tail)


def g4_eq():
    """g4 where treeg takes a G4: tree1 over its four chunks."""
    P = paths(2, "c")
    t = "(cb + c : U32)"
    cs = ["c"] + [f"(c + {i} : U32)" for i in range(1, 4)]
    ts = [t] + [f"({t} + {i} : U32)" for i in range(1, 4)]
    gchs = lambda arr: [sndc(f"B3.gch({arr}, {cs[i]}, {ts[i]}, 0)") for i in range(4)]
    S = gchs("x")
    chunks = lambda arr: [f"B3.chunk({arr}, {p}, cb, nch, last, 0)" for p in P]
    fcs = [FC("x", WL(i, "(c << 8n : U32)"), f"({t} + {i} : U32)") for i in range(4)]
    P4 = lambda ys, rf: f"B3.parent(B3.parent({ys[0]}, {ys[1]}, 0), B3.parent({ys[2]}, {ys[3]}, 0), {rf})"
    T2 = lambda arr: t1(2, "True{}", f"({arr}, {arr})", "c", 4, "rf")
    g4 = lambda arr: f"B3.g4({arr}, c, {t}, rf)"
    inv = f"{{Nat.is_le(Nat.add({TN('c')}, 4n), {TN('nch')}) == True{{}} : Bool}}"
    ef = "{B3.full((c + 4 : U32), nch, last) == True{} : Bool}"
    lines, bi = wmatch("r", [f"z{i}" for i in range(7)], "  ")
    tr_ = lambda q, z, f: f"tr(arr => {q}, {z}, x, e{z}0, {f})"
    rw = lambda e, motive: f"{bi}%{e} :\n{bi}  {motive}\n"
    b = []
    # The LHS: g.fin to snd, g4.val, each chunk's CV, the lanes' word offsets.
    b.append(rw(f"Equal.sym(B3.CV, B3.g.fin({g4('x')}), {sndc(g4('x'))}, "
                f"{tr_('{B3.g.fin(' + g4('arr') + ') == ' + sndc(g4('arr')) + ' : B3.CV}', 'z0', 'gfin.snd(' + g4('z0') + ')')})",
                f"{{_ == {T2('x')} : B3.CV}}"))
    b.append(rw(f"Equal.sym(B3.CV, {sndc(g4('x'))}, {P4(S, 'rf')}, "
                f"{tr_('{' + sndc(g4('arr')) + ' == ' + P4(gchs('arr'), 'rf') + ' : B3.CV}', 'z1', f'g4.val(z1, c, {t}, rf)')})",
                f"{{_ == {T2('x')} : B3.CV}}"))
    cur = list(S)
    for i in range(4):
        hole = list(cur)
        hole[i] = "_"
        W = f"({cs[i]} << 8n : U32)"
        fact = tr_("{" + sndc(f"B3.gch(arr, {cs[i]}, {ts[i]}, 0)") + " == " + FC("arr", W, ts[i]) + " : B3.CV}",
                   f"z{2 + i}", f"gch.fc(z{2 + i}, {cs[i]}, {ts[i]}, 0)")
        b.append(rw(f"Equal.sym(B3.CV, {S[i]}, {FC('x', W, ts[i])}, {fact})", f"{{{P4(hole, 'rf')} == {T2('x')} : B3.CV}}"))
        cur[i] = FC("x", W, ts[i])
    for i in range(1, 4):
        hole = list(cur)
        hole[i] = FC("x", "_", ts[i])
        b.append(rw(f"Equal.sym(U32, ({cs[i]} << 8n : U32), {WL(i, '(c << 8n : U32)')}, A.u.shln_add(c, {i}, 8n))",
                    f"{{{P4(hole, 'rf')} == {T2('x')} : B3.CV}}"))
        cur[i] = fcs[i]
    hole = list(cur)
    hole[0] = FC("x", "(c << 8n : U32)", "_")
    b.append(rw(f"A.u.add_zero_r({t})", f"{{{P4(hole, 'rf')} == {T2('x')} : B3.CV}}"))
    cur[0] = fcs[0]
    # The RHS: tree1 to its four chunks, each its full chain.
    b.append(rw(f"Equal.sym(B3.CV, {T2('x')}, {P4(chunks('x'), 'rf')}, "
                f"{tr_('{' + T2('arr') + ' == ' + P4(chunks('arr'), 'rf') + ' : B3.CV}', 'z6', 'tree1.u2(z6, c, cb, nch, last, rf)')})",
                f"{{{P4(cur, 'rf')} == _ : B3.CV}}"))
    facts = []
    for i, p in enumerate(P[:-1]):
        e = f"({p} + 1 : U32)"
        j, pf = norm(e)
        nl = f"nonlast(c, nch, {j}, 4n, inv, {{==}})"
        facts.append(nl if pf is None else
                     f"Equal.trans(Bool, U32.is_eq({e}, nch), U32.is_eq((c + {j} : U32), nch), False{{}}, "
                     f"Equal.cong(U32, Bool, z => U32.is_eq(z, nch), {e}, (c + {j} : U32), {pf}), {nl})")
    e3 = f"({P[3]} + 1 : U32)"
    j3, pf3 = norm(e3)
    assert j3 == 4
    eb3 = f"Equal.cong(U32, Bool, z => U32.is_eq(z, nch), {e3}, (c + 4 : U32), {pf3})"
    el3 = "full.last.b((c + 4 : U32), nch, last, U32.is_eq((c + 4 : U32), nch), {==}, ef)"
    ceqs = [f"chunk.eq{i}(x, c, cb, nch, last, {facts[i]})" for i in range(3)]
    ceqs.append(f"chunk.eq.g3(x, c, cb, nch, last, U32.is_eq((c + 4 : U32), nch), {eb3}, {el3})")
    rcur = chunks("x")
    for i in range(4):
        hole = list(rcur)
        hole[i] = "_"
        b.append(rw(f"Equal.sym(B3.CV, {chunks('x')[i]}, {fcs[i]}, {ceqs[i]})", f"{{{P4(cur, 'rf')} == {P4(hole, 'rf')} : B3.CV}}"))
        rcur[i] = fcs[i]
    b.append(f"{bi}{{==}}\n")
    goal = f"{{B3.g.fin({g4('x')}) == {T2('x')} : B3.CV}}"
    return (chunk_last(3, P[3], "chunk.eq.g3") +
            f"\ndef g4.eq.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, +inv: {inv}, +ef: {ef}, r: Wits(x, 7n)) -> {goal}:\n" +
            "".join(lines) + "".join(b) + f'''
# A GPU 4-chunk leaf is tree1 over its chunks, where the span holds it whole.
law g4.eq:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +inv: {inv}
  for +ef: {ef}
  {goal}

def g4.eq(x, c, cb, nch, last, rf, inv, ef):
  g4.eq.h(x, c, cb, nch, last, rf, inv, ef, wits(6n, x))
''')


def quarters_eq(name, sub, s):
    """name where treeg takes it whole: tree1 over its 4s chunks, from sub.eq
    on each quarter (s chunks apart)."""
    k = DEPTH[name]
    d = DEPTH[sub]
    t = "(cb + c : U32)"
    cs = ["c"] + [f"(c + {s * i} : U32)" for i in range(1, 4)]
    ts = [t] + [f"({t} + {s * i} : U32)" for i in range(1, 4)]
    qs = ["c", f"(c + {s} : U32)", f"(c + {2 * s} : U32)", f"((c + {2 * s} : U32) + {s} : U32)"]
    P4 = lambda ys, rf: f"B3.parent(B3.parent({ys[0]}, {ys[1]}, 0), B3.parent({ys[2]}, {ys[3]}, 0), {rf})"
    V = lambda arr, i: sndc(f"B3.{sub}({arr}, {cs[i]}, {ts[i]}, 0)")
    GF = lambda arr, c_, t_: f"B3.g.fin(B3.{sub}({arr}, {c_}, {t_}, 0))"
    T = lambda c_, arr="x": t1(d, "True{}", f"({arr}, {arr})", c_, s, "0")
    Tk = lambda arr: t1(k, "True{}", f"({arr}, {arr})", "c", 4 * s, "rf")
    top = lambda arr: f"B3.{name}({arr}, c, {t}, rf)"
    inv = f"{{Nat.is_le(Nat.add({TN('c')}, {4 * s}n), {TN('nch')}) == True{{}} : Bool}}"
    ef = f"{{B3.full((c + {4 * s} : U32), nch, last) == True{{}} : Bool}}"
    names = ["z0", "z1", "z2"] + [f"q{i}{w}" for i in range(4) for w in "ab"]
    lines, bi = wmatch("r", names, "  ")
    tr_ = lambda q, z, f: f"tr(arr => {q}, {z}, x, e{z}0, {f})"
    rw = lambda e, motive: f"{bi}%{e} :\n{bi}  {motive}\n"
    R = P4([T(q) for q in qs], "rf")
    b = []
    b.append(rw(f"Equal.sym(B3.CV, B3.g.fin({top('x')}), {sndc(top('x'))}, "
                f"{tr_('{B3.g.fin(' + top('arr') + ') == ' + sndc(top('arr')) + ' : B3.CV}', 'z0', 'gfin.snd(' + top('z0') + ')')})",
                f"{{_ == {Tk('x')} : B3.CV}}"))
    Vs = [V("x", i) for i in range(4)]
    b.append(rw(f"Equal.sym(B3.CV, {sndc(top('x'))}, {P4(Vs, 'rf')}, "
                f"{tr_('{' + sndc(top('arr')) + ' == ' + P4([V('arr', i) for i in range(4)], 'rf') + ' : B3.CV}', 'z1', f'{name}.val(z1, c, {t}, rf)')})",
                f"{{_ == {Tk('x')} : B3.CV}}"))
    b.append(rw(f"Equal.sym(B3.CV, {Tk('x')}, {R}, "
                f"{tr_('{' + Tk('arr') + ' == ' + P4([T(q, 'arr') for q in qs], 'rf') + ' : B3.CV}', 'z2', f'tree1.u{k}(z2, c, cb, nch, last, rf)')})",
                f"{{{P4(Vs, 'rf')} == _ : B3.CV}}"))
    cur = list(Vs)
    for i in range(4):
        qi = qs[i]
        za, zb = f"q{i}a", f"q{i}b"
        # sub.eq on the quarter, with its fullness from the node's.
        if i == 0:
            invi = f"A.n.le_trans(Nat.add({TN('c')}, {s}n), Nat.add({TN('c')}, {4 * s}n), {TN('nch')}, A.n.add_le({TN('c')}, {s}n, {4 * s}n, {{==}}), inv)"
            efi = f"full.from_lt((c + {s} : U32), nch, last, lt.off(c, nch, {s}, {4 * s}n, inv, {{==}}))"
        else:
            j, pf = norm(qi)
            invc = f"inv.off(c, nch, {j}, {s}n, {4 * s}n, inv, {{==}})"
            invi = invc if pf is None else (
                f"Equal.trans(Bool, Nat.is_le(Nat.add({TN(qi)}, {s}n), {TN('nch')}), Nat.is_le(Nat.add({TN(f'(c + {j} : U32)')}, {s}n), {TN('nch')}), True{{}}, "
                f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add(U32.to_nat(z), {s}n), {TN('nch')}), {qi}, (c + {j} : U32), {pf}), {invc})")
            e_ = f"({qi} + {s} : U32)"
            j2, pf2 = norm(e_)
            eff = f"full.from_lt((c + {j2} : U32), nch, last, lt.off(c, nch, {j2}, {4 * s}n, inv, {{==}}))" if i < 3 else "ef"
            efi = (f"Equal.trans(Bool, B3.full({e_}, nch, last), B3.full((c + {j2} : U32), nch, last), True{{}}, "
                   f"Equal.cong(U32, Bool, z => B3.full(z, nch, last), {e_}, (c + {j2} : U32), {pf2}), {eff})")
        Q = tr_("{" + GF("arr", qi, f"(cb + {qi} : U32)") + " == " + T(qi, "arr") + " : B3.CV}", za,
                f"{sub}.eq({za}, {qi}, cb, nch, last, 0, {invi}, {efi})")
        # snd of the quarter, as name.val has it, to its g.fin.
        G = tr_("{" + GF("arr", cs[i], ts[i]) + " == " + V("arr", i) + " : B3.CV}", zb, f"gfin.snd(B3.{sub}({zb}, {cs[i]}, {ts[i]}, 0))")
        if i == 0:
            Qp = Q
        else:
            j, pf = norm(qi)
            if pf is None:
                idx = f"Equal.cong(U32, B3.CV, z => {GF('x', qi, 'z')}, {ts[i]}, (cb + {qi} : U32), A.u.add_assoc(cb, c, {j}))"
            else:
                step1 = f"Equal.cong(U32, B3.CV, z => {GF('x', 'z', ts[i])}, {cs[i]}, {qi}, Equal.sym(U32, {qi}, {cs[i]}, {pf}))"
                ctr = (f"Equal.trans(U32, {ts[i]}, (cb + {cs[i]} : U32), (cb + {qi} : U32), A.u.add_assoc(cb, c, {j}), "
                       f"Equal.cong(U32, U32, z => (cb + z : U32), {cs[i]}, {qi}, Equal.sym(U32, {qi}, {cs[i]}, {pf})))")
                step2 = f"Equal.cong(U32, B3.CV, z => {GF('x', qi, 'z')}, {ts[i]}, (cb + {qi} : U32), {ctr})"
                idx = f"Equal.trans(B3.CV, {GF('x', cs[i], ts[i])}, {GF('x', qi, ts[i])}, {GF('x', qi, f'(cb + {qi} : U32)')}, {step1}, {step2})"
            Qp = f"Equal.trans(B3.CV, {GF('x', cs[i], ts[i])}, {GF('x', qi, f'(cb + {qi} : U32)')}, {T(qi)}, {idx}, {Q})"
        full = f"Equal.trans(B3.CV, {Vs[i]}, {GF('x', cs[i], ts[i])}, {T(qi)}, Equal.sym(B3.CV, {GF('x', cs[i], ts[i])}, {Vs[i]}, {G}), {Qp})"
        hole = list(cur)
        hole[i] = "_"
        b.append(rw(f"Equal.sym(B3.CV, {Vs[i]}, {T(qi)}, {full})", f"{{{P4(hole, 'rf')} == {R} : B3.CV}}"))
        cur[i] = T(qi)
    b.append(f"{bi}{{==}}\n")
    goal = f"{{B3.g.fin({top('x')}) == {Tk('x')} : B3.CV}}"
    return (f"\ndef {name}.eq.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, +inv: {inv}, +ef: {ef}, r: Wits(x, {len(names)}n)) -> {goal}:\n" +
            "".join(lines) + "".join(b) + f'''
# A GPU {4 * s}-chunk leaf is tree1 over its chunks, where the span holds it whole.
law {name}.eq:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +inv: {inv}
  for +ef: {ef}
  {goal}

def {name}.eq(x, c, cb, nch, last, rf, inv, ef):
  {name}.eq.h(x, c, cb, nch, last, rf, inv, ef, wits({len(names) - 1}n, x))
''')


def text():
    return (scalar_loop() + gch() + "".join(chain(n, s, k) for n, s, k in LEVELS) +
            "".join(tree1_unroll(d) for d in (0, 2, 4)) + g4_eq() +
            quarters_eq("g16", "g4", 4) + quarters_eq("g64", "g16", 16))
