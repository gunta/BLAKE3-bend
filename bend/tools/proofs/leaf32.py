"""32-chunk leaves: leaf32.eq proves that where tree8 takes a Leaf32, the
result is tree1's scalar tree over those chunks, for every array: leaf32 is
four groups' leaf8s under two levels of parents (fold.par on par8.lane),
and tree1 over 32 chunks is four 8-chunk subtrees (leaf8.eq each)."""
from .common import L, CS, TN, F8, fst8, wmatch
from .leaf8 import t1, norm


def fold_par():
    X = "B3.par8(p, q)"
    lanes = [f"cv.at(L{i}{{}}, {X})" for i in range(L)]
    refs = [f"par.ref(L{i}{{}}, p, q)" for i in range(L)]
    pl = [f"cv.at(L{i}{{}}, p)" for i in range(L)]
    ql = [f"cv.at(L{i}{{}}, q)" for i in range(L)]
    rhs = "B3.parent(B3.fold8(p, 0), B3.fold8(q, 0), rf)"
    b = [f"  %Equal.sym(B3.CV, B3.fold8({X}, rf), {F8(lanes, 'rf')}, fold8.lanes({X}, rf)) :\n    {{_ == {rhs} : B3.CV}}\n"]
    cur = list(lanes)
    for i in range(L):
        hole = list(cur)
        hole[i] = "_"
        b.append(f"  %Equal.sym(B3.CV, {lanes[i]}, {refs[i]}, par8.lane(L{i}{{}}, p, q)) :\n    {{{F8(hole, 'rf')} == {rhs} : B3.CV}}\n")
        cur[i] = refs[i]
    b.append(f"  %Equal.sym(B3.CV, B3.fold8(p, 0), {F8(pl, '0')}, fold8.lanes(p, 0)) :\n"
             f"    {{{F8(cur, 'rf')} == B3.parent(_, B3.fold8(q, 0), rf) : B3.CV}}\n")
    b.append(f"  %Equal.sym(B3.CV, B3.fold8(q, 0), {F8(ql, '0')}, fold8.lanes(q, 0)) :\n"
             f"    {{{F8(cur, 'rf')} == B3.parent({F8(pl, '0')}, _, rf) : B3.CV}}\n")
    b.append("  {==}\n")
    return f'''
# fold8 of a par8 level is the parent of the two halves' folds.
law fold.par:
  for +p: B3.CV8
  for +q: B3.CV8
  for +rf: U32
  {{B3.fold8({X}, rf) == {rhs} : B3.CV}}

def fold.par(p, q, rf):
''' + "".join(b)


def c8_eta():
    W2 = "(w + B3.step(q) : U32)"
    c8l = lambda n, r: f"B3.c8.go({n}, {r}, w, cv, ctr, fl)"
    return f'''
# One copy per block left.
def Bun1(-a: Array<U32>, p: Nat) -> Type:
  match p:
    case 0n:
      Unit
    case 1n+q:
      Wits(a, 1n) & Bun1(a, q)

def BunS1(-a: Array<U32>, p: Nat) -> Type:
  Exists(Array<U32>, s => {{s == a : Array<U32>}} & Bun1(a, p))

def bun1.add2(-a: Array<U32>, +q: Nat, -s: Array<U32>, +es: {{s == a : Array<U32>}}, w: Wits(s, 2n), rest: Bun1(a, q)) -> BunS1(a, 1n+q):
  match w:
    case (s2, w2):
      match w2:
        case (es2, lvl):
          (s2, (eq.trans(s2, s, a, es2, es), (tr(c => Wits(c, 1n), s, a, es, lvl), rest)))

def bun1.add(-a: Array<U32>, +q: Nat, r: BunS1(a, q)) -> BunS1(a, 1n+q):
  match r:
    case (s, r2):
      match r2:
        case (es, rest):
          bun1.add2(a, q, s, es, wits(1n, s), rest)

law bun1:
  for +p: Nat
  for a: Array<U32>
  BunS1(a, p)

def bun1(p, a):
  match p:
    case 0n:
      (a, ({{==}}, Unit{{}}))
    case 1n+q:
      bun1.add(a, q, bun1(q, a))

# The 8-lane chunk loop hands its array back.
law c8.eta:
  for +n: Nat
  for -a0: Array<U32>
  for r: Array<U32> & B3.B128
  for +er: {{{fst8("r")} == a0 : Array<U32>}}
  for +w: U32
  for +cv: B3.CV8
  for +ctr: U32
  for +fl: U32
  for bun: Bun1(a0, n)
  {{{c8l("n", "r")} == (a0, Pair.snd(Array<U32>, B3.CV8, {c8l("n", "r")})) : Array<U32> & B3.CV8}}

def c8.eta(n, a0, r, er, w, cv, ctr, fl, bun):
  match n:
    case 0n:
      match r:
        case (a, +m):
          _ = bun
          %er : {{(a, cv) == (_, cv) : Array<U32> & B3.CV8}}
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
                      +f = eq.trans({fst8(f"B3.ld8(a, {W2})")}, a, a0, tr(arr => {{{fst8(f"B3.ld8(arr, {W2})")} == arr : Array<U32>}}, x1, a,
                        eq.trans(x1, a0, a, e1, Equal.sym(Array<U32>, a, a0, er)), ld8.fst(x1, {W2})), er)
                      c8.eta(q, a0, B3.ld8(a, {W2}), f, {W2}, B3.compress8(cv, m, ctr, 1, 64, (fl .|. B3.endf(q) : U32)), ctr, 0, rest)
'''


def group_eta():
    gw = "(c << 8n : U32)"
    G = lambda arr: f"B3.group({arr}, c, t)"
    c8g = lambda arr: f"B3.c8.go(16n, B3.ld8({arr}, {gw}), {gw}, B3.IV8(), t, {CS})"
    lines, bi = wmatch("r", ["x1", "x2"], "  ")
    lines = [ln.replace("(+ex10, ", "(+ex1o, ").replace("(+ex20, ", "(+ex2o, ") for ln in lines]
    body = (f"{bi}+ex1 = eq.trans(x1, s, a, ex1o, es)\n{bi}+ex2 = eq.trans(x2, s, a, ex2o, es)\n"
            f"{bi}+f = eq.trans({fst8(f'B3.ld8(x1, {gw})')}, x1, a, tr(arr => {{{fst8(f'B3.ld8(arr, {gw})')} == arr : Array<U32>}}, x2, x1, "
            f"eq.trans(x2, a, x1, ex2, Equal.sym(Array<U32>, x1, a, ex1)), ld8.fst(x2, {gw})), ex1)\n"
            f"{bi}tr(arr => {{{c8g('arr')} == (a, Pair.snd(Array<U32>, B3.CV8, {c8g('arr')})) : Array<U32> & B3.CV8}}, x1, a, ex1,\n"
            f"{bi}  c8.eta(16n, a, B3.ld8(x1, {gw}), f, {gw}, B3.IV8(), t, {CS}, bb))\n")
    goal = f"{{{G('a')} == (a, Pair.snd(Array<U32>, B3.CV8, {G('a')})) : Array<U32> & B3.CV8}}"
    return (f"\ndef group.eta.h2(-a: Array<U32>, +c: U32, +t: U32, -s: Array<U32>, +es: {{s == a : Array<U32>}}, "
            f"r: Wits(s, 2n), bb: Bun1(a, 16n)) -> {goal}:\n" + "".join(lines) + body + f'''
def group.eta.h1(-a: Array<U32>, +c: U32, +t: U32, r: BunS1(a, 16n)) -> {goal}:
  match r:
    case (s, r2):
      match r2:
        case (+es, bb):
          group.eta.h2(a, c, t, s, es, wits(1n, s), bb)

# A group hands its array back.
law group.eta:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  {goal}

def group.eta(a, c, t):
  group.eta.h1(a, c, t, bun1(16n, a))
''')


def fold_par2():
    lhs = "B3.fold8(B3.par8(B3.par8(g0, g1), B3.par8(g2, g3)), rf)"
    rhs = "B3.parent(B3.parent(B3.fold8(g0, 0), B3.fold8(g1, 0), 0), B3.parent(B3.fold8(g2, 0), B3.fold8(g3, 0), 0), rf)"
    return f'''
law fold.par2:
  for +g0: B3.CV8
  for +g1: B3.CV8
  for +g2: B3.CV8
  for +g3: B3.CV8
  for +rf: U32
  {{{lhs} == {rhs} : B3.CV}}

def fold.par2(g0, g1, g2, g3, rf):
  %Equal.sym(B3.CV, {lhs}, B3.parent(B3.fold8(B3.par8(g0, g1), 0), B3.fold8(B3.par8(g2, g3), 0), rf), fold.par(B3.par8(g0, g1), B3.par8(g2, g3), rf)) :
    {{_ == {rhs} : B3.CV}}
  %Equal.sym(B3.CV, B3.fold8(B3.par8(g0, g1), 0), B3.parent(B3.fold8(g0, 0), B3.fold8(g1, 0), 0), fold.par(g0, g1, 0)) :
    {{B3.parent(_, B3.fold8(B3.par8(g2, g3), 0), rf) == {rhs} : B3.CV}}
  %Equal.sym(B3.CV, B3.fold8(B3.par8(g2, g3), 0), B3.parent(B3.fold8(g2, 0), B3.fold8(g3, 0), 0), fold.par(g2, g3, 0)) :
    {{B3.parent(B3.parent(B3.fold8(g0, 0), B3.fold8(g1, 0), 0), _, rf) == {rhs} : B3.CV}}
  {{==}}
'''


def leaf32_split():
    cs = ["c", "(c + 8 : U32)", "(c + 16 : U32)", "(c + 24 : U32)"]
    ts = ["t", "(t + 8 : U32)", "(t + 16 : U32)", "(t + 24 : U32)"]
    Gk = lambda arr, k: f"B3.group({arr}, {cs[k]}, {ts[k]})"
    Sk = lambda arr, k: f"Pair.snd(Array<U32>, B3.CV8, {Gk(arr, k)})"
    l8 = lambda k: f"B3.leaf8(a, {cs[k]}, {ts[k]}, 0)"
    rhs32 = f"B3.parent(B3.parent({l8(0)}, {l8(1)}, 0), B3.parent({l8(2)}, {l8(3)}, 0), rf)"
    names = [f"u{k}" for k in range(4)] + [f"y{k}" for k in range(4)]
    lines, bi = wmatch("r", names, "  ")
    Gs = [Sk("a", k) for k in range(4)]
    states = [
        "B3.leaf8.fin(B3.leaf32.s0(_, c, t), rf)",
        f"B3.leaf8.fin(B3.leaf32.s1(_, c, t, {Gs[0]}), rf)",
        f"B3.leaf8.fin(B3.leaf32.s2(_, c, t, B3.par8({Gs[0]}, {Gs[1]})), rf)",
        f"B3.leaf8.fin(B3.leaf32.s3(_, B3.par8({Gs[0]}, {Gs[1]}), {Gs[2]}), rf)",
    ]
    b = []
    # Each group, on leaf32's chain and in its leaf8, hands the array back.
    for k in range(4):
        fact = (f"tr(arr => {{{Gk('arr', k)} == (arr, {Sk('arr', k)}) : Array<U32> & B3.CV8}}, "
                f"u{k}, a, eu{k}0, group.eta(u{k}, {cs[k]}, {ts[k]}))")
        tk = lambda j: ("B3.leaf8.fin(_, 0)" if j == k else
                        f"B3.leaf8.fin((a, {Gs[j]}), 0)" if j < k else l8(j))
        rh = f"B3.parent(B3.parent({tk(0)}, {tk(1)}, 0), B3.parent({tk(2)}, {tk(3)}, 0), rf)"
        b.append(f"{bi}%Equal.sym(Array<U32> & B3.CV8, {Gk('a', k)}, (a, {Gs[k]}), {fact}) :\n{bi}  {{{states[k]} == {rh} : B3.CV}}\n")
    # Then fold.par2 on the four groups' CVs, each named by a copy of a.
    for k in range(4):
        b.append(f"{bi}+gy{k} = {Sk(f'y{k}', k)}\n")
    fact = f"fold.par2({', '.join(f'gy{k}' for k in range(4))}, rf)"
    cur = [Sk(f"y{k}", k) for k in range(4)]
    for k in range(4):
        def mk(arr):
            ls = list(cur)
            ls[k] = Sk(arr, k)
            l_ = f"B3.fold8(B3.par8(B3.par8({ls[0]}, {ls[1]}), B3.par8({ls[2]}, {ls[3]})), rf)"
            r_ = f"B3.parent(B3.parent(B3.fold8({ls[0]}, 0), B3.fold8({ls[1]}, 0), 0), B3.parent(B3.fold8({ls[2]}, 0), B3.fold8({ls[3]}, 0), 0), rf)"
            return f"{{{l_} == {r_} : B3.CV}}"
        fact = f"tr(arr => {mk('arr')}, y{k}, a, ey{k}0, {fact})"
        cur[k] = Sk("a", k)
    b.append(f"{bi}{fact}\n")
    goal = f"{{B3.leaf32(a, c, t, rf) == {rhs32} : B3.CV}}"
    return (f"\ndef leaf32.split.h(-a: Array<U32>, +c: U32, +t: U32, +rf: U32, r: Wits(a, 8n)) -> {goal}:\n" +
            "".join(lines) + "".join(b) + f'''
# 32 full chunks on the 8-lane path: four groups' 8-chunk leaves under two
# levels of parents.
law leaf32.split:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +rf: U32
  {goal}

def leaf32.split(a, c, t, rf):
  leaf32.split.h(a, c, t, rf, wits(7n, a))
''')


def offsets():
    return f'''
law le.add_r:
  for +j: Nat
  for +n: Nat
  {{Nat.is_le(j, Nat.add(j, n)) == True{{}} : Bool}}

def le.add_r(j, n):
  match j:
    case 0n:
      match n:
        case 0n:
          {{==}}
        case 1n+q:
          {{==}}
    case 1n+p:
      le.add_r(p, n)

# c + j + n <= nch when c + m <= nch and j + n <= m.
law inv.off:
  for +c: U32
  for +nch: U32
  for +j: U32
  for +n: Nat
  for +m: Nat
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, m), {TN("nch")}) == True{{}} : Bool}}
  for +ej: {{Nat.is_le(Nat.add({TN("j")}, n), m) == True{{}} : Bool}}
  {{Nat.is_le(Nat.add({TN("(c + j : U32)")}, n), {TN("nch")}) == True{{}} : Bool}}

def inv.off(c, nch, j, n, m, inv, ej):
  +cj = Nat.add({TN("c")}, {TN("j")})
  +jle = A.n.le_trans({TN("j")}, Nat.add({TN("j")}, n), m, le.add_r({TN("j")}, n), ej)
  +le = A.n.le_trans(cj, Nat.add({TN("c")}, m), {TN("nch")}, A.n.add_le({TN("c")}, {TN("j")}, m, jle), inv)
  %Equal.sym(Nat, {TN("(c + j : U32)")}, cj, A.u.tn_add(c, j, nch, le)) : {{Nat.is_le(Nat.add(_, n), {TN("nch")}) == True{{}} : Bool}}
  %Equal.sym(Nat, Nat.add(Nat.add({TN("c")}, {TN("j")}), n), Nat.add({TN("c")}, Nat.add({TN("j")}, n)), A.add_assoc({TN("c")}, {TN("j")}, n)) : {{Nat.is_le(_, {TN("nch")}) == True{{}} : Bool}}
  A.n.le_trans(Nat.add({TN("c")}, Nat.add({TN("j")}, n)), Nat.add({TN("c")}, m), {TN("nch")}, A.n.add_le({TN("c")}, Nat.add({TN("j")}, n), m, ej), inv)

# c + j < nch when c + m <= nch and j < m.
law lt.off:
  for +c: U32
  for +nch: U32
  for +j: U32
  for +m: Nat
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, m), {TN("nch")}) == True{{}} : Bool}}
  for +ej: {{Nat.is_lt({TN("j")}, m) == True{{}} : Bool}}
  {{U32.is_lt((c + j : U32), nch) == True{{}} : Bool}}

def lt.off(c, nch, j, m, inv, ej):
  +cj = Nat.add({TN("c")}, {TN("j")})
  +le = A.n.le_trans(cj, Nat.add({TN("c")}, m), {TN("nch")}, A.n.add_le({TN("c")}, {TN("j")}, m, A.n.lt_to_le({TN("j")}, m, ej)), inv)
  %Equal.sym(Bool, U32.is_lt((c + j : U32), nch), Nat.is_lt({TN("(c + j : U32)")}, {TN("nch")}), A.u.is_lt_nat((c + j : U32), nch)) : {{_ == True{{}} : Bool}}
  %Equal.sym(Nat, {TN("(c + j : U32)")}, cj, A.u.tn_add(c, j, nch, le)) : {{Nat.is_lt(_, {TN("nch")}) == True{{}} : Bool}}
  A.n.lt_le(cj, Nat.add({TN("c")}, m), {TN("nch")}, A.n.add_lt({TN("c")}, {TN("j")}, m, ej), inv)

law full.from_lt:
  for +e: U32
  for +nch: U32
  for +last: U32
  for +el: {{U32.is_lt(e, nch) == True{{}} : Bool}}
  {{B3.full(e, nch, last) == True{{}} : Bool}}

def full.from_lt(e, nch, last, el):
  %Equal.sym(Bool, U32.is_lt(e, nch), True{{}}, el) : {{(_ || (U32.is_eq(e, nch) && U32.is_eq(last, 1024))) == True{{}} : Bool}}
  {{==}}
'''


T3 = lambda c, rf="0": t1(3, "True{}", "(x, x)", c, 8, rf)
C3 = ["c", "(c + 8 : U32)", "(c + 16 : U32)", "((c + 16 : U32) + 8 : U32)"]
R5 = f"B3.parent(B3.parent({T3(C3[0])}, {T3(C3[1])}, 0), B3.parent({T3(C3[2])}, {T3(C3[3])}, 0), rf)"
T5 = t1(5, "True{}", "(x, x)", "c", 32, "rf")


def tree1_d5():
    c4 = ["c", "(c + 16 : U32)"]
    lv1 = f"B3.parent({t1(4, 'True{}', '_', c4[0], 16, 0)}, {t1(4, 'True{}', '_', c4[1], 16, 0)}, rf)"
    lv2 = (f"B3.parent(B3.parent({t1(3, 'True{}', '_', C3[0], 8, 0)}, {t1(3, 'True{}', '_', C3[1], 8, 0)}, 0), "
           f"B3.parent({t1(3, 'True{}', '_', C3[2], 8, 0)}, {t1(3, 'True{}', '_', C3[3], 8, 0)}, 0), rf)")
    clone = lambda z: f"tr(arr => {{Array.clone(U32, arr) == (arr, arr) : Array<U32> & Array<U32>}}, {z}, x, e{z}0, clone.dup({z}))"
    lines, bi = wmatch("r", ["z1", "z2"], "  ")
    body = [f"{bi}%Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, x), (x, x), {clone(z)}) :\n{bi}  {{{lv} == {R5} : B3.CV}}\n"
            for lv, z in ((lv1, "z1"), (lv2, "z2"))]
    body.append(f"{bi}{{==}}\n")
    goal = f"{{{T5} == {R5} : B3.CV}}"
    return (f"\ndef tree1.d5.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, r: Wits(x, 2n)) -> {goal}:\n" +
            "".join(lines) + "".join(body) + f'''
# tree1 over 32 chunks from c is four 8-chunk subtrees under 3 parents.
law tree1.d5:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {goal}

def tree1.d5(x, c, cb, nch, last, rf):
  tree1.d5.h(x, c, cb, nch, last, rf, wits(1n, x))
''')


def leaf32_eq():
    cs = ["c", "(c + 8 : U32)", "(c + 16 : U32)", "(c + 24 : U32)"]
    t = "(cb + c : U32)"
    ts = [t, f"({t} + 8 : U32)", f"({t} + 16 : U32)", f"({t} + 24 : U32)"]
    l8 = lambda k: f"B3.leaf8(x, {cs[k]}, {ts[k]}, 0)"
    SPL = f"B3.parent(B3.parent({l8(0)}, {l8(1)}, 0), B3.parent({l8(2)}, {l8(3)}, 0), rf)"
    inv32 = f"{{Nat.is_le(Nat.add({TN('c')}, 32n), {TN('nch')}) == True{{}} : Bool}}"
    ef32 = "{B3.full((c + 32 : U32), nch, last) == True{} : Bool}"
    names = ["xs", "xt"] + [f"q{k}{s}" for k in range(4) for s in "ab"]
    lines, bi = wmatch("r", names, "  ")
    b = [f"{bi}%Equal.sym(B3.CV, B3.leaf32(x, c, {t}, rf), {SPL}, tr(arr => {{B3.leaf32(arr, c, {t}, rf) == "
         f"{SPL.replace('B3.leaf8(x,', 'B3.leaf8(arr,')} : B3.CV}}, xs, x, exs0, leaf32.split(xs, c, {t}, rf))) :\n"
         f"{bi}  {{_ == {T5} : B3.CV}}\n",
         f"{bi}%Equal.sym(B3.CV, {T5}, {R5}, tr(arr => {{{T5.replace('(x, x)', '(arr, arr)')} == {R5.replace('(x, x)', '(arr, arr)')} : B3.CV}}, "
         f"xt, x, ext0, tree1.d5(xt, c, cb, nch, last, rf))) :\n"
         f"{bi}  {{{SPL} == _ : B3.CV}}\n"]
    cur = [l8(k) for k in range(4)]
    for k in range(4):
        ck = C3[k]
        if k == 0:
            invk = f"A.n.le_trans(Nat.add({TN('c')}, 8n), Nat.add({TN('c')}, 32n), {TN('nch')}, A.n.add_le({TN('c')}, 8n, 32n, {{==}}), inv)"
            efk = "full.from_lt((c + 8 : U32), nch, last, lt.off(c, nch, 8, 32n, inv, {==}))"
        else:
            j, pf = norm(ck)
            invk_c = f"inv.off(c, nch, {j}, 8n, 32n, inv, {{==}})"
            invk = invk_c if pf is None else (
                f"Equal.trans(Bool, Nat.is_le(Nat.add({TN(ck)}, 8n), {TN('nch')}), Nat.is_le(Nat.add({TN(f'(c + {j} : U32)')}, 8n), {TN('nch')}), True{{}}, "
                f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add(U32.to_nat(z), 8n), {TN('nch')}), {ck}, (c + {j} : U32), {pf}), {invk_c})")
            e8 = f"({ck} + 8 : U32)"
            j8, pf8 = norm(e8)
            eff = f"full.from_lt((c + {j8} : U32), nch, last, lt.off(c, nch, {j8}, 32n, inv, {{==}}))" if k < 3 else "ef"
            efk = (f"Equal.trans(Bool, B3.full({e8}, nch, last), B3.full((c + {j8} : U32), nch, last), True{{}}, "
                   f"Equal.cong(U32, Bool, z => B3.full(z, nch, last), {e8}, (c + {j8} : U32), {pf8}), {eff})")
        Q = f"leaf8.eq(x, q{k}a, eq{k}a0, q{k}b, eq{k}b0, {ck}, cb, nch, last, 0, {invk}, {efk})"
        if k == 0:
            Qp = Q
        else:
            j, pf = norm(ck)
            if pf is None:
                idx = f"Equal.cong(U32, B3.CV, z => B3.leaf8(x, {ck}, z, 0), {ts[k]}, (cb + {ck} : U32), A.u.add_assoc(cb, c, {j}))"
            else:
                step1 = f"Equal.cong(U32, B3.CV, z => B3.leaf8(x, z, {ts[k]}, 0), {cs[k]}, {ck}, Equal.sym(U32, {ck}, {cs[k]}, {pf}))"
                ctr = (f"Equal.trans(U32, {ts[k]}, (cb + {cs[k]} : U32), (cb + {ck} : U32), A.u.add_assoc(cb, c, {j}), "
                       f"Equal.cong(U32, U32, z => (cb + z : U32), {cs[k]}, {ck}, Equal.sym(U32, {ck}, {cs[k]}, {pf})))")
                step2 = f"Equal.cong(U32, B3.CV, z => B3.leaf8(x, {ck}, z, 0), {ts[k]}, (cb + {ck} : U32), {ctr})"
                idx = f"Equal.trans(B3.CV, {l8(k)}, B3.leaf8(x, {ck}, {ts[k]}, 0), B3.leaf8(x, {ck}, (cb + {ck} : U32), 0), {step1}, {step2})"
            Qp = f"Equal.trans(B3.CV, {l8(k)}, B3.leaf8(x, {ck}, (cb + {ck} : U32), 0), {T3(ck)}, {idx}, {Q})"
        hole = list(cur)
        hole[k] = "_"
        lhs_h = f"B3.parent(B3.parent({hole[0]}, {hole[1]}, 0), B3.parent({hole[2]}, {hole[3]}, 0), rf)"
        b.append(f"{bi}%Equal.sym(B3.CV, {l8(k)}, {T3(ck)}, {Qp}) :\n{bi}  {{{lhs_h} == {R5} : B3.CV}}\n")
        cur[k] = T3(ck)
    b.append(f"{bi}{{==}}\n")
    goal = f"{{B3.leaf32(x, c, {t}, rf) == {T5} : B3.CV}}"
    return (f"\ndef leaf32.eq.h(-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, +inv: {inv32}, +ef: {ef32}, "
            f"r: Wits(x, {len(names)}n)) -> {goal}:\n" + "".join(lines) + "".join(b) + f'''
# A full 32-chunk node: the CPU's 32-chunk leaf is the scalar tree over its
# chunks, for every array and every span that holds it whole.
law leaf32.eq:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +inv: {inv32}
  for +ef: {ef32}
  {goal}

def leaf32.eq(x, c, cb, nch, last, rf, inv, ef):
  leaf32.eq.h(x, c, cb, nch, last, rf, inv, ef, wits({len(names) - 1}n, x))
''')


def text():
    return fold_par() + c8_eta() + group_eta() + fold_par2() + leaf32_split() + offsets() + tree1_d5() + leaf32_eq()
