"""The GPU tree: gpu.tree proves treeg is tree1 node for node (kind1 splits
where tree1 does; its flat leaves are g4.eq, g16.eq, g64.eq and its strided
lanes gquad.eq), and gpu.at closes hash1's entry point like cpu.at."""
from .common import TN, wmatch
from .tree import F, KP, K1, I
from .quads import T, SH, rw, le, offs, CLX, CLONE

TS = "~share"
CL = CLX


def TG(k, ku, d, aa, c, n, rf):
    return f"B3.treeg({TS}, {k}, {ku}, {d}, {aa}, {c}, {n}, cb, nch, last, lv, {rf})"


def T1(k, b, aa, c, n, rf):
    return f"B3.tree1({TS}, {k}, {b}, {aa}, {c}, {n}, cb, nch, last, {rf})"


def KIND1(ku, n, c):
    return f"B3.kind1({ku}, {n}, {c}, nch, last, lv)"


def QG(ku):
    """kind1's test for strided lanes: leaf level 6 and a node deeper than 6."""
    return f"(U32.is_eq(lv, 6) && U32.is_gt({ku}, 6))"


INV = f"{{Nat.is_le(Nat.add({TN('c')}, {TN('n')}), {TN('nch')}) == True{{}} : Bool}}"
NODES = ["GDown", "GSplit", "G4", "G16", "G64", "GQuad"]


def gquad():
    """The node that hands a whole subtree of 2^(6+q) chunks to 2^q strided
    lanes: fold4 of qt's four quarters is tree1, split twice."""
    k = "6n+q"
    lhs = TG(k, "ku", "B3.GQuad{}", "(x, x)", "c", "n", "rf")
    rhs0 = T1(k, "True{}", "(x, x)", "c", "n", "rf")
    goal = f"{{{lhs} == {rhs0} : B3.CV}}"
    Fk = F("ku", "n", "c")
    E = "(c + n : U32)"
    H4, H5, H6 = SH("4n+q"), SH("5n+q"), SH("6n+q")
    P4, P5, P6 = "A.pow2(4n+q)", "A.pow2(5n+q)", "A.pow2(6n+q)"
    st = "U32.shln(16, q)"
    os = [o.replace("st", st) for o in offs("c")]
    os2 = ["c", f"(c + {H4} : U32)", f"(c + {H5} : U32)", f"((c + {H5} : U32) + {H4} : U32)"]
    en_ = f"U32.shln(1, {TN('ku')})"
    absurd = f'''      _ = w
      +en = A.u.eq_sound(n, {en_}, A.and.l(U32.is_eq(n, {en_}), B3.full({E}, nch, last), ef))
      +g1 = Equal.trans(Bool, U32.is_gt({en_}, {H5}), U32.is_gt(n, {H5}), True{{}},
        Equal.cong(U32, Bool, z => U32.is_gt(z, {H5}), {en_}, n, Equal.sym(U32, n, {en_}, en)), eb)
      +g2 = Equal.trans(Bool, U32.is_gt(U32.shln(1, {TN('U32.from_nat(6n+q)')}), {H5}), U32.is_gt({en_}, {H5}), True{{}},
        Equal.cong(U32, Bool, z => U32.is_gt(U32.shln(1, U32.to_nat(z)), {H5}), U32.from_nat(6n+q), ku, Equal.sym(U32, ku, U32.from_nat(6n+q), eku)), g1)
      +g3 = Equal.trans(Bool, U32.is_gt(U32.shln(1, {TN('U32.from_nat(32n)')}), {SH('31n')}), U32.is_gt(U32.shln(1, {TN('U32.from_nat(6n+q)')}), {H5}), True{{}},
        Equal.cong(Nat, Bool, y => U32.is_gt(U32.shln(1, U32.to_nat(U32.from_nat(6n+y))), U32.shln(1, 5n+y)), 26n, q,
          Equal.sym(Nat, q, 26n, A.n.top(q, 25n, ek, e25))), g2)
      Empty.absurd({goal}, A.absurd.ft(g3))
'''
    zs = [f"z{i}" for i in range(1, 6)]
    lines, bi = wmatch("w", zs, "      ")
    lets = [
        f"+k6 = Equal.trans(U32, (ku - 6 : U32), (U32.from_nat(6n+q) - 6 : U32), U32.from_nat(q), "
        f"Equal.cong(U32, U32, z => (z - 6 : U32), ku, U32.from_nat(6n+q), eku), "
        f"Equal.trans(U32, (U32.from_nat(6n+q) - 6 : U32), U32.from_nat(Nat.sub(q, 0n)), U32.from_nat(q), "
        f"Equal.sym(U32, U32.from_nat(Nat.sub(q, 0n)), (U32.from_nat(6n+q) - 6 : U32), A.u.fn_sub(6n+q, 6n, n.le_zero(q))), "
        f"Equal.cong(Nat, U32, z => U32.from_nat(z), Nat.sub(q, 0n), q, A.n.sub_zero(q))))",
        f"+tq = Equal.trans(Nat, {TN('(ku - 6 : U32)')}, {TN('U32.from_nat(q)')}, q, "
        f"Equal.cong(U32, Nat, z => U32.to_nat(z), (ku - 6 : U32), U32.from_nat(q), k6), A.u.tn_fn(q, 25, e25))",
        f"+en = A.u.eq_sound(n, {en_}, A.and.l(U32.is_eq(n, {en_}), B3.full({E}, nch, last), ef))",
        f"+tk = Equal.trans(Nat, {TN('ku')}, {TN('U32.from_nat(6n+q)')}, 6n+q, "
        f"Equal.cong(U32, Nat, z => U32.to_nat(z), ku, U32.from_nat(6n+q), eku), A.u.tn_fn(6n+q, 32, ek))",
        f"+nn = Equal.trans(U32, n, {en_}, {H6}, en, Equal.cong(Nat, U32, z => U32.shln(1, z), {TN('ku')}, 6n+q, tk))",
        f"+efull = A.and.r(U32.is_eq(n, {en_}), B3.full({E}, nch, last), ef)",
        f"+tcn0 = A.u.tn_add(c, n, nch, inv)",
        f"+ee = Equal.trans(Bool, Nat.is_le({TN(E)}, {TN('nch')}), Nat.is_le(Nat.add({TN('c')}, {TN('n')}), {TN('nch')}), True{{}}, "
        f"Equal.cong(Nat, Bool, z => Nat.is_le(z, {TN('nch')}), {TN(E)}, Nat.add({TN('c')}, {TN('n')}), tcn0), inv)",
        f"+tn = Equal.trans(Nat, {TN('n')}, {TN(H6)}, {P6}, Equal.cong(U32, Nat, z => U32.to_nat(z), n, {H6}, nn), A.sh.nat(6n+q, e25))",
        f"+tcn = Equal.trans(Nat, {TN(E)}, Nat.add({TN('c')}, {TN('n')}), Nat.add({TN('c')}, {P6}), tcn0, "
        f"Equal.cong(Nat, Nat, z => Nat.add({TN('c')}, z), {TN('n')}, {P6}, tn))",
        f"+htop = Equal.trans(Bool, Nat.is_le(Nat.add({TN('c')}, {P6}), {TN(E)}), Nat.is_le(Nat.add({TN('c')}, {P6}), Nat.add({TN('c')}, {P6})), True{{}}, "
        f"Equal.cong(Nat, Bool, z => Nat.is_le(Nat.add({TN('c')}, {P6}), z), {TN(E)}, Nat.add({TN('c')}, {P6}), tcn), A.n.le_refl(Nat.add({TN('c')}, {P6})))",
        f"+e4 = A.le.succ_le(4n+q, 31n, ek)",
        f"+hL = hyp.l(c, {P5}, {E}, htop)",
        f"+hR = hyp.r(c, 5n+q, {E}, ek, htop)",
        f"+g0 = hyp.l(c, {P4}, {E}, hL)",
        f"+g1 = hyp.r(c, 4n+q, {E}, e4, hL)",
        f"+g2 = hyp.l((c + {H5} : U32), {P4}, {E}, hR)",
        f"+g3 = hyp.r((c + {H5} : U32), 4n+q, {E}, e4, hR)",
        f"+eo1 = Equal.cong(U32, U32, z => (c + z : U32), {st}, {H4}, A.sh16(q))",
        f"+eo2 = Equal.cong(U32, U32, z => (c + (z << 1n : U32) : U32), {st}, {H4}, A.sh16(q))",
        f"+eo3 = Equal.trans(U32, {os[3]}, (c + ({H4} + {H5} : U32) : U32), {os2[3]}, "
        f"Equal.cong(U32, U32, z => (c + (z + (z << 1n : U32) : U32) : U32), {st}, {H4}, A.sh16(q)), "
        f"Equal.trans(U32, (c + ({H4} + {H5} : U32) : U32), (c + ({H5} + {H4} : U32) : U32), {os2[3]}, "
        f"Equal.cong(U32, U32, z => (c + z : U32), ({H4} + {H5} : U32), ({H5} + {H4} : U32), U32.add_comm({H4}, {H5})), "
        f"Equal.sym(U32, {os2[3]}, (c + ({H5} + {H4} : U32) : U32), A.u.add_assoc(c, {H5}, {H4}))))",
    ]
    hq = ["g0"] + [f"Equal.trans(Bool, Nat.is_le(Nat.add({TN(os[i])}, {P4}), {TN(E)}), Nat.is_le(Nat.add({TN(os2[i])}, {P4}), {TN(E)}), True{{}}, "
                   f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add(U32.to_nat(z), {P4}), {TN(E)}), {os[i]}, {os2[i]}, eo{i}), g{i})" for i in range(1, 4)]
    TQ = lambda o, arr="x": T("Nat.add(4n, q)", "True{}", f"({arr}, {arr})", o, SH("Nat.add(4n, q)"), "0")
    QT = (f"qt(q, x, tr(arr => Wits(arr, 7n), z2, x, ez20, wits(6n, z2)), c, {st}, cb, nch, last, {E}, ee, efull, e4, "
          f"{', '.join(hq)})")
    CV4 = f"B3.CV4{{{', '.join(TQ(o) for o in os)}}}"
    lhs3 = f"B3.fold4({CV4}, rf)"
    T5 = lambda o: T("5n+q", "True{}", "(x, x)", o, H5, "0")
    T4 = lambda o: T("4n+q", "True{}", "(x, x)", o, H4, "0")
    # tree1.halfT at m = j + q: tree1 over 2^(j+2+q) chunks from o, halved.
    half = lambda z, j, o, rf, em: (
        f"tr(arr => {{{T(f'{j + 2}n+q', 'True{}', '(arr, arr)', o, SH(f'{j + 2}n+q'), rf)} == "
        f"B3.parent({T(f'{j + 1}n+q', 'True{}', '(arr, arr)', o, SH(f'{j + 1}n+q'), '0')}, "
        f"{T(f'{j + 1}n+q', 'True{}', '(arr, arr)', f'({o} + {SH(f'{j + 1}n+q')} : U32)', SH(f'{j + 1}n+q'), '0')}, {rf}) : B3.CV}}, "
        f"{z}, x, e{z}0, tree1.halfT({j}n+q, {z}, {o}, cb, nch, last, {rf}, {em}))")
    P = lambda a, b, rf: f"B3.parent({a}, {b}, {rf})"
    b = [f"{bi}{l}\n" for l in lets]
    b.append(rw(bi, f"Equal.sym(Nat, {TN('(ku - 6 : U32)')}, q, tq)",
                f"{{B3.fold4(B3.qtree({TS}, _, {CL}, c, (cb + c : U32), U32.shln(16, _)), rf) == {rhs0} : B3.CV}}"))
    b.append(rw(bi, f"Equal.sym(Array<U32> & Array<U32>, {CL}, (x, x), {CLONE.format(z='z1')})",
                f"{{B3.fold4(B3.qtree({TS}, q, _, c, (cb + c : U32), {st}), rf) == {rhs0} : B3.CV}}"))
    b.append(rw(bi, f"Equal.sym(B3.CV4, B3.qtree({TS}, q, (x, x), c, (cb + c : U32), {st}), {CV4}, {QT})",
                f"{{B3.fold4(_, rf) == {rhs0} : B3.CV}}"))
    b.append(rw(bi, f"Equal.sym(U32, n, {H6}, nn)", f"{{{lhs3} == {T1(k, 'True{}', '(x, x)', 'c', '_', 'rf')} : B3.CV}}"))
    top = T(k, "True{}", "(x, x)", "c", H6, "rf")
    halves = P(T5("c"), T5(os2[2]), "rf")
    b.append(rw(bi, f"Equal.sym(B3.CV, {top}, {halves}, {half('z3', 4, 'c', 'rf', 'ek')})", f"{{{lhs3} == _ : B3.CV}}"))
    q0 = P(T4("c"), T4(os2[1]), "0")
    b.append(rw(bi, f"Equal.sym(B3.CV, {T5('c')}, {q0}, {half('z4', 3, 'c', '0', 'e4')})",
                f"{{{lhs3} == {P('_', T5(os2[2]), 'rf')} : B3.CV}}"))
    q1 = P(T4(os2[2]), T4(os2[3]), "0")
    b.append(rw(bi, f"Equal.sym(B3.CV, {T5(os2[2])}, {q1}, {half('z5', 3, os2[2], '0', 'e4')})",
                f"{{{lhs3} == {P(q0, '_', 'rf')} : B3.CV}}"))
    cur = list(os2)
    for i in (3, 2, 1):
        hole = list(cur)
        hole[i] = "_"
        b.append(rw(bi, f"eo{i}", f"{{{lhs3} == {P(P(T4(hole[0]), T4(hole[1]), '0'), P(T4(hole[2]), T4(hole[3]), '0'), 'rf')} : B3.CV}}"))
        cur[i] = os[i]
    b.append(f"{bi}{{==}}\n")
    common_fors = f'''  for +ku: U32
  for +eku: {{ku == U32.from_nat(6n+q) : U32}}
  for +ek: {le("6n+q", "32n")}
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +lv: U32
  for +rf: U32
  for +inv: {INV}
  for +eb: {{B3.big(6n+q, n) == True{{}} : Bool}}
  for +ef: {{{Fk} == True{{}} : Bool}}
'''
    plv = lambda j: TG(f"{j}n", "ku", "B3.GQuad{}", "(x, x)", "c", "n", "rf") + " == " + T1(f"{j}n", "True{}", "(x, x)", "c", "n", "rf")
    s = []
    ind = "  "
    s.append(f"{ind}match p:\n")
    for j in range(5):
        s.append(f"{ind}  case 0n:\n{ind}    _ = x\n{ind}    Empty.absurd({{{plv(j + 1)} : B3.CV}}, A.absurd.ft(g6))\n")
        nxt = "q" if j == 4 else f"p{j + 1}"
        s.append(f"{ind}  case 1n+{nxt}:\n")
        ind += "    "
        if j < 4:
            s.append(f"{ind}match {nxt}:\n")
    s.append(f"{ind}gquad.eq(q, x, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef)\n")
    goal_p = f"{{{TG('1n+p', 'ku', 'B3.GQuad{}', '(x, x)', 'c', 'n', 'rf')} == {T1('1n+p', 'True{}', '(x, x)', 'c', 'n', 'rf')} : B3.CV}}"
    return f'''
# The strided-lane node
# ---------------------

# A whole, full subtree of 2^(6+q) chunks handed to 2^q strided lanes is
# tree1 over it (q <= 25: at q = 26 it would be 2^32 chunks, which kind1's
# split test rules out).
law gquad.b:
  for +q: Nat
  for b: Bool
  for +e25: {{Nat.is_le(q, 25n) == b : Bool}}
  for -x: Array<U32>
  for w: Wits(x, 5n)
{common_fors}  {goal}

def gquad.b(q, b, e25, x, w, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef):
  match b:
    case False{{}}:
{absurd}    case True{{}}:
''' + "".join(lines) + "".join(b) + f'''
law gquad.eq:
  for +q: Nat
  for x: Array<U32>
{common_fors}  {goal}

def gquad.eq(q, x, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef):
  gquad.b(q, Nat.is_le(q, 25n), {{==}}, x, wits(4n, x), ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef)

# The GQuad node at depth 1 + p, from treeg's own decision: p >= 5.
law gquad.p:
  for +p: Nat
  for x: Array<U32>
  for +ku: U32
  for +eku: {{ku == U32.from_nat(1n+p) : U32}}
  for +ek: {le("1n+p", "32n")}
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +lv: U32
  for +rf: U32
  for +inv: {INV}
  for +eb: {{B3.big(1n+p, n) == True{{}} : Bool}}
  for +ef: {{{Fk} == True{{}} : Bool}}
  for +g6: {{U32.is_gt(U32.from_nat(1n+p), 6) == True{{}} : Bool}}
  {goal_p}

def gquad.p(p, x, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef, g6):
''' + "".join(s)


def helpers():
    cases = "".join(f"    case B3.{d}{{}}:\n      {{==}}\n" for d in NODES)
    return f'''
# The GPU tree
# ------------

# At depth 0 both trees hash the one chunk, whatever kind treeg was handed.
law g.zero:
  for +ku: U32
  for d: B3.Node1
  for -a1: Array<U32>
  for -a2: Array<U32>
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +lv: U32
  for +rf: U32
  {{{TG("0n", "ku", "d", "(a1, a2)", "c", "n", "rf")} == {T1("0n", "False{}", "(a1, a2)", "c", "n", "rf")} : B3.CV}}

def g.zero(ku, d, a1, a2, c, n, cb, nch, last, lv, rf):
  match d:
{cases}'''


def kb(arg):
    return f"B3.kind1.big(ku, n, c, nch, last, lv, {arg})"


def rewrite(eq, val, motive_kind):
    return (f"{I}%Equal.sym(Bool, {eq[0]}, {val}, {eq[1]}) :\n"
            f"{I}  {{{TG(K1, 'ku', motive_kind, CL, 'c', 'n', 'rf')} == {T1(K1, 'True{}', CL, 'c', 'n', 'rf')} : B3.CV}}\n")


def node_cases():
    goal_rhs = T1(K1, "B3.big(1n+p, n)", CL, "c", "n", "rf")
    common = [
        f"{I}+ekp = A.le.succ_le(p, 32n, ek)\n",
        f"{I}+kd = Equal.trans(U32, {KP}, (U32.from_nat(1n+p) - 1 : U32), U32.from_nat(p), "
        f"Equal.cong(U32, U32, z => (z - 1 : U32), ku, U32.from_nat(1n+p), eku), A.u.down(p))\n",
        f"{I}+tp = Equal.trans(Nat, {TN(KP)}, {TN('U32.from_nat(p)')}, p, "
        f"Equal.cong(U32, Nat, z => U32.to_nat(z), {KP}, U32.from_nat(p), kd), A.u.tn_fn(p, 32, ekp))\n",
        f"{I}%Equal.sym(Nat, {TN(KP)}, p, tp) :\n"
        f"{I}  {{{TG(K1, 'ku', kb('U32.is_gt(n, U32.shln(1, _))'), CL, 'c', 'n', 'rf')} == {goal_rhs} : B3.CV}}\n",
    ]

    def r2(val):
        return (f"{I}%Equal.sym(Bool, B3.big(1n+p, n), {val}, eb) :\n"
                f"{I}  {{{TG(K1, 'ku', kb('_'), CL, 'c', 'n', 'rf')} == {T1(K1, '_', CL, 'c', 'n', 'rf')} : B3.CV}}\n")
    rW = lambda v: rewrite((F("ku", "n", "c"), "ef"), v, "B3.kind1.whole(ku, lv, _)")
    rQ = lambda v: rewrite((QG("ku"), "eg"), v, "B3.kind1.wq(_, ku, lv)")
    rV = lambda v: rewrite(("U32.is_le(ku, lv)", "ev"), v, "B3.kind1.full(ku, _)")
    r64 = lambda v: rewrite(("U32.is_eq(ku, 6)", "es6"), v, "B3.kind1.at64(_, ku)")
    r16 = lambda v: rewrite(("U32.is_eq(ku, 4)", "es4"), v, "B3.kind1.at16(_, ku)")
    r4 = lambda v: rewrite(("U32.is_eq(ku, 2)", "es2"), v, "B3.kind1.at4(_)")

    def rclone(node):
        return (f"{I}%Equal.sym(Array<U32> & Array<U32>, {CL}, (x, x), ecl) :\n"
                f"{I}  {{{TG(K1, 'ku', node, '_', 'c', 'n', 'rf')} == {T1(K1, 'True{}', '_', 'c', 'n', 'rf')} : B3.CV}}\n")

    def ih(c, n, rf, pkx, inv):
        return (f"gpu.tree(p, x, {pkx}, {KP}, kd, ekp, {c}, {n}, cb, nch, last, lv, {rf}, {inv}, B3.big(p, {n}), {{==}}, "
                f"{F(KP, n, c)}, {{==}}, {QG(KP)}, {{==}}, U32.is_le({KP}, lv), {{==}}, U32.is_eq({KP}, 6), {{==}}, "
                f"U32.is_eq({KP}, 4), {{==}}, U32.is_eq({KP}, 2), {{==}})")

    down = common + [r2("False{}"), f"{I}{ih('c', 'n', 'rf', '(x1, (x2, (e1, (e2, ecl))))', 'inv')}\n"]
    h = "U32.shln(1, p)"
    n2 = f"(n - {h} : U32)"
    c2 = f"(c + {h} : U32)"
    gt = (f"Equal.trans(Bool, Nat.is_gt({TN('n')}, {TN(h)}), U32.is_gt(n, {h}), True{{}}, "
          f"Equal.sym(Bool, U32.is_gt(n, {h}), Nat.is_gt({TN('n')}, {TN(h)}), A.u.is_gt_nat(n, {h})), eb)")

    def split_tail():
        cw = lambda z, e: f"tr(arr => CloneW(arr), {z}, x, {e}, clone.w({z}))"
        ihl = ih("c", h, "0", cw("x1", "e1"), f"inv.left(c, n, {h}, nch, inv, lt)")
        ihr = ih(c2, n2, "0", cw("x2", "e2"), f"inv.split(c, n, {h}, nch, inv, lt)")
        tgl = TG("p", KP, KIND1(KP, h, "c"), CL, "c", h, "0")
        tgr = TG("p", KP, KIND1(KP, n2, c2), CL, c2, n2, "0")
        t1l = T1("p", f"B3.big(p, {h})", CL, "c", h, "0")
        t1r = T1("p", f"B3.big(p, {n2})", CL, c2, n2, "0")
        rhs = f"B3.parent({t1l}, {t1r}, rf)"
        return [f"{I}+lt = A.n.gt_lt({TN('n')}, {TN(h)}, {gt})\n",
                f"{I}%Equal.sym(B3.CV, {tgl}, {t1l}, {ihl}) :\n{I}  {{B3.parent(_, {tgr}, rf) == {rhs} : B3.CV}}\n",
                f"{I}%Equal.sym(B3.CV, {tgr}, {t1r}, {ihr}) :\n{I}  {{B3.parent({t1l}, _, rf) == {rhs} : B3.CV}}\n",
                f"{I}{{==}}\n"]

    def leaf(kv, nv, name):
        s = [f"{I}+kq = A.u.eq_sound(ku, {kv}, es{kv})\n",
             f"{I}+pv = Equal.cong(Nat, Nat, z => pred(z), 1n+p, {kv}n, k.val(p, ku, {kv}, eku, ek, kq))\n",
             f"{I}+fk = Equal.trans(Bool, {F(str(kv), 'n', 'c')}, {F('ku', 'n', 'c')}, True{{}}, "
             f"Equal.cong(U32, Bool, z => {F('z', 'n', 'c')}, {kv}, ku, Equal.sym(U32, ku, {kv}, kq)), ef)\n",
             f"{I}+nq = A.u.eq_sound(n, {nv}, A.and.l(U32.is_eq(n, {nv}), B3.full((c + n : U32), nch, last), fk))\n",
             f"{I}+efull = A.and.r(U32.is_eq(n, {nv}), B3.full((c + n : U32), nch, last), fk)\n",
             f"{I}+invk = Equal.trans(Bool, Nat.is_le(Nat.add({TN('c')}, {nv}n), {TN('nch')}), Nat.is_le(Nat.add({TN('c')}, {TN('n')}), {TN('nch')}), True{{}}, "
             f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add({TN('c')}, U32.to_nat(z)), {TN('nch')}), {nv}, n, Equal.sym(U32, n, {nv}, nq)), inv)\n",
             f"{I}+efk = Equal.trans(Bool, B3.full((c + {nv} : U32), nch, last), B3.full((c + n : U32), nch, last), True{{}}, "
             f"Equal.cong(U32, Bool, z => B3.full((c + z : U32), nch, last), {nv}, n, Equal.sym(U32, n, {nv}, nq)), efull)\n"]
        lhs = f"B3.g.fin(B3.{name}(x, c, (cb + c : U32), rf))"
        s.append(f"{I}%Equal.sym(Nat, p, {kv - 1}n, pv) :\n{I}  {{{lhs} == {T1('1n+_', 'True{}', '(x, x)', 'c', 'n', 'rf')} : B3.CV}}\n")
        s.append(f"{I}%Equal.sym(U32, n, {nv}, nq) :\n{I}  {{{lhs} == {T1(f'{kv}n', 'True{}', '(x, x)', 'c', '_', 'rf')} : B3.CV}}\n")
        s.append(f"{I}_ = x2\n")
        s.append(f"{I}tr(arr => {{B3.g.fin(B3.{name}(arr, c, (cb + c : U32), rf)) == {T1(f'{kv}n', 'True{}', '(arr, arr)', 'c', str(nv), 'rf')} : B3.CV}}, "
                 f"x1, x, e1, {name}.eq(x1, c, cb, nch, last, rf, invk, efk))\n")
        return s

    g6 = (f"Equal.trans(Bool, U32.is_gt(U32.from_nat(1n+p), 6), U32.is_gt(ku, 6), True{{}}, "
          f"Equal.cong(U32, Bool, z => U32.is_gt(z, 6), U32.from_nat(1n+p), ku, Equal.sym(U32, ku, U32.from_nat(1n+p), eku)), "
          f"A.and.r(U32.is_eq(lv, 6), U32.is_gt(ku, 6), eg))")
    quad = [f"{I}_ = x2\n",
            f"{I}tr(arr => {{{TG(K1, 'ku', 'B3.GQuad{}', '(arr, arr)', 'c', 'n', 'rf')} == {T1(K1, 'True{}', '(arr, arr)', 'c', 'n', 'rf')} : B3.CV}}, "
            f"x1, x, e1, gquad.p(p, x1, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, eb, ef, {g6}))\n"]
    T_, F_ = "True{}", "False{}"
    pre = common + [r2(T_)]
    split1 = pre + [rW(F_), rclone("B3.GSplit{}")] + split_tail()
    quadc = pre + [rW(T_), rQ(T_), rclone("B3.GQuad{}")] + quad
    split2 = pre + [rW(T_), rQ(F_), rV(F_), rclone("B3.GSplit{}")] + split_tail()
    g64 = pre + [rW(T_), rQ(F_), rV(T_), r64(T_), rclone("B3.G64{}")] + leaf(6, 64, "g64")
    g16 = pre + [rW(T_), rQ(F_), rV(T_), r64(F_), r16(T_), rclone("B3.G16{}")] + leaf(4, 16, "g16")
    g4 = pre + [rW(T_), rQ(F_), rV(T_), r64(F_), r16(F_), r4(T_), rclone("B3.G4{}")] + leaf(2, 4, "g4")
    split3 = pre + [rW(T_), rQ(F_), rV(T_), r64(F_), r16(F_), r4(F_), rclone("B3.GSplit{}")] + split_tail()
    c = "                        case "
    pats = [("False{} _ _ _ _ _ _", down), ("True{} False{} _ _ _ _ _", split1), ("True{} True{} True{} _ _ _ _", quadc),
            ("True{} True{} False{} False{} _ _ _", split2), ("True{} True{} False{} True{} True{} _ _", g64),
            ("True{} True{} False{} True{} False{} True{} _", g16), ("True{} True{} False{} True{} False{} False{} True{}", g4),
            ("True{} True{} False{} True{} False{} False{} False{}", split3)]
    return "".join(f"{c}{p}:\n" + "".join(body) for p, body in pats)


def gpu_tree():
    open_pk = '''      match pk:
        case (x1, pk2):
          match pk2:
            case (x2, pk3):
              match pk3:
                case (+e1, pk4):
                  match pk4:
                    case (+e2, ecl):
'''
    decisions = [("b", "B3.big(k, n)"), ("f", F("ku", "n", "c")), ("g", QG("ku")), ("v", "U32.is_le(ku, lv)"),
                 ("s6", "U32.is_eq(ku, 6)"), ("s4", "U32.is_eq(ku, 4)"), ("s2", "U32.is_eq(ku, 2)")]
    fors = "".join(f"  for {v}: Bool\n  for +e{v}: {{{t} == {v} : Bool}}\n" for v, t in decisions)
    args = ", ".join(f"{v}, e{v}" for v, _ in decisions)
    return f'''
# The GPU tree is the scalar tree, node for node: treeg's kind (computed
# from ku, a U32 copy of the depth, and the leaf level lv) takes tree1's
# split exactly where tree1 does, and its flat leaves and strided lanes are
# the scalar subtrees. Each node holds a clone of x and two live copies (pk).
law gpu.tree:
  for +k: Nat
  for -x: Array<U32>
  for pk: CloneW(x)
  for +ku: U32
  for +eku: {{ku == U32.from_nat(k) : U32}}
  for +ek: {le("k", "32n")}
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +lv: U32
  for +rf: U32
  for +inv: {INV}
{fors}  {{{TG("k", "ku", KIND1("ku", "n", "c"), CL, "c", "n", "rf")} ==
    {T1("k", "B3.big(k, n)", CL, "c", "n", "rf")} : B3.CV}}

def gpu.tree(k, x, pk, ku, eku, ek, c, n, cb, nch, last, lv, rf, inv, {args}):
  match k:
    case 0n:
{open_pk}                      _ = x1
                      _ = x2
                      %Equal.sym(Array<U32> & Array<U32>, {CL}, (x, x), ecl) :
                        {{{TG("0n", "ku", KIND1("ku", "n", "c"), "_", "c", "n", "rf")} == {T1("0n", "B3.big(0n, n)", "_", "c", "n", "rf")} : B3.CV}}
                      g.zero(ku, {KIND1("ku", "n", "c")}, x, x, c, n, cb, nch, last, lv, rf)
    case 1n+p:
{open_pk}                      match b f g v s6 s4 s2:
''' + node_cases()


def top():
    F0 = F("ku", "nch", "0")
    return f'''
law gpu.go:
  for +k: Nat
  for a: Array<U32>
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +ek: {le("k", "32n")}
  {{B3.hash1.go(~share, k, a, cb, nch, last, rf) == ref.go(k, a, cb, nch, last, rf) : B3.CV}}

def gpu.go(k, a, cb, nch, last, rf, ek):
  match k:
    case 0n:
      {{==}}
    case 1n+p:
      +ku = U32.from_nat(1n+p)
      +lv = B3.level(ku)
      gpu.tree(1n+p, a, clone.w(a), ku, {{==}}, ek, 0, nch, cb, nch, last, lv, rf, A.n.le_refl({TN("nch")}),
        B3.big(1n+p, nch), {{==}}, {F0}, {{==}}, {QG("ku")}, {{==}}, U32.is_le(ku, lv), {{==}},
        U32.is_eq(ku, 6), {{==}}, U32.is_eq(ku, 4), {{==}}, U32.is_eq(ku, 2), {{==}})

# The GPU's tree (flat leaves, strided lanes) is the scalar tree, for every
# array and every span.
law gpu.at:
  for a: Array<U32>
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {{B3.hash1.at(~share, a, cb, nch, last, rf) == ref.go(B3.depth(nch), a, cb, nch, last, rf) : B3.CV}}

def gpu.at(a, cb, nch, last, rf):
  gpu.go(B3.depth(nch), a, cb, nch, last, rf, depth.le32(nch))
'''


def text():
    return gquad() + helpers() + gpu_tree() + top()
