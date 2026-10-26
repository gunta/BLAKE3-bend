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


def text():
    return (scalar_loop() + gch() + "".join(chain(n, s, k) for n, s, k in LEVELS) +
            "".join(tree1_unroll(d) for d in (0, 2, 4)))
