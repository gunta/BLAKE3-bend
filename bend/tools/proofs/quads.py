"""The GPU's strided lanes: a lane (quad) is four 16-chunk leaves st chunks
apart, a fork of 2^r lanes (qtree) is four scalar subtrees of 16 * 2^r
chunks, and the node that hands a whole subtree to them (GQuad) is tree1."""
from .common import TN, wmatch
from .gpu import sndc

TS = "~share"
CLX = "Array.clone(U32, x)"
CLONE = "tr(arr => {{Array.clone(U32, arr) == (arr, arr) : Array<U32> & Array<U32>}}, {z}, x, e{z}0, clone.dup({z}))"


def T(k, b, aa, c, n, rf):
    return f"B3.tree1({TS}, {k}, {b}, {aa}, {c}, {n}, cb, nch, last, {rf})"


def SH(m):
    return f"U32.shln(1, {m})"


def rw(bi, e, motive):
    return f"{bi}%{e} :\n{bi}  {motive}\n"


def le(a, b):
    return f"{{Nat.is_le({a}, {b}) == True{{}} : Bool}}"


# Quad offsets from c: what quad.s0..s3 compute (st chunks between groups).
X = ["", "st", "(st << 1n : U32)", "(st + (st << 1n : U32) : U32)"]


def offs(c):
    return [c] + [f"({c} + {x} : U32)" for x in X[1:]]


def ranges():
    return f'''
# Ranges of a full span
# ---------------------
#
# A range that ends at or before the end en of a full range ends inside the
# span (it is full): its end is below nch, or it is en itself.

law sub.full.b:
  for b: Bool
  for +y: U32
  for +l: U32
  for +en: U32
  for +nch: U32
  for +last: U32
  for +ee: {le(TN("en"), TN("nch"))}
  for +fe: {{B3.full(en, nch, last) == True{{}} : Bool}}
  for +ey: {le(f"Nat.add({TN('y')}, {TN('l')})", TN("en"))}
  for +eb: {{Nat.is_lt(Nat.add({TN('y')}, {TN('l')}), {TN('nch')}) == b : Bool}}
  {{B3.full((y + l : U32), nch, last) == True{{}} : Bool}}

def sub.full.b(b, y, l, en, nch, last, ee, fe, ey, eb):
  match b:
    case True{{}}:
      +es = A.u.tn_add(y, l, en, ey)
      full.from_lt((y + l : U32), nch, last,
        Equal.trans(Bool, U32.is_lt((y + l : U32), nch), Nat.is_lt({TN("(y + l : U32)")}, {TN("nch")}), True{{}}, A.u.is_lt_nat((y + l : U32), nch),
          Equal.trans(Bool, Nat.is_lt({TN("(y + l : U32)")}, {TN("nch")}), Nat.is_lt(Nat.add({TN('y')}, {TN('l')}), {TN("nch")}), True{{}},
            Equal.cong(Nat, Bool, z => Nat.is_lt(z, {TN("nch")}), {TN("(y + l : U32)")}, Nat.add({TN('y')}, {TN('l')}), es), eb)))
    case False{{}}:
      +es = A.u.tn_add(y, l, en, ey)
      +te = Equal.trans(Nat, {TN("(y + l : U32)")}, Nat.add({TN('y')}, {TN('l')}), {TN("en")}, es,
        A.n.squeeze(Nat.add({TN('y')}, {TN('l')}), {TN("en")}, {TN("nch")}, ey, ee, eb))
      +ue = Equal.trans(U32, (y + l : U32), U32.from_nat({TN("(y + l : U32)")}), en,
        Equal.sym(U32, U32.from_nat({TN("(y + l : U32)")}), (y + l : U32), A.u.fn_tn((y + l : U32))),
        Equal.trans(U32, U32.from_nat({TN("(y + l : U32)")}), U32.from_nat({TN("en")}), en,
          Equal.cong(Nat, U32, z => U32.from_nat(z), {TN("(y + l : U32)")}, {TN("en")}, te), A.u.fn_tn(en)))
      %Equal.sym(U32, (y + l : U32), en, ue) : {{B3.full(_, nch, last) == True{{}} : Bool}}
      fe

law sub.full:
  for +y: U32
  for +l: U32
  for +en: U32
  for +nch: U32
  for +last: U32
  for +ee: {le(TN("en"), TN("nch"))}
  for +fe: {{B3.full(en, nch, last) == True{{}} : Bool}}
  for +ey: {le(f"Nat.add({TN('y')}, {TN('l')})", TN("en"))}
  {{B3.full((y + l : U32), nch, last) == True{{}} : Bool}}

def sub.full(y, l, en, nch, last, ee, fe, ey):
  sub.full.b(Nat.is_lt(Nat.add({TN('y')}, {TN('l')}), {TN('nch')}), y, l, en, nch, last, ee, fe, ey, {{==}})

# Where a range of 2p chunks from o fits, so does its first half...
law hyp.l:
  for +o: U32
  for +p: Nat
  for +en: U32
  for +h: {le(f"Nat.add({TN('o')}, Nat.double(p))", TN("en"))}
  {le(f"Nat.add({TN('o')}, p)", TN("en"))}

def hyp.l(o, p, en, h):
  A.n.le_trans(Nat.add({TN('o')}, p), Nat.add({TN('o')}, Nat.double(p)), {TN('en')},
    A.n.add_le({TN('o')}, p, Nat.double(p), A.le.dbl(p)), h)

# ...and its second half, 2^m chunks on.
law hyp.r:
  for +o: U32
  for +m: Nat
  for +en: U32
  for +em: {le("m", "31n")}
  for +h: {le(f"Nat.add({TN('o')}, Nat.double(A.pow2(m)))", TN("en"))}
  {le(f"Nat.add({TN(f'(o + {SH('m')} : U32)')}, A.pow2(m))", TN("en"))}

def hyp.r(o, m, en, em, h):
  +th = A.sh.nat(m, em)
  +hl = hyp.l(o, A.pow2(m), en, h)
  +b = Equal.trans(Bool, Nat.is_le(Nat.add({TN('o')}, {TN(SH('m'))}), {TN('en')}), Nat.is_le(Nat.add({TN('o')}, A.pow2(m)), {TN('en')}), True{{}},
    Equal.cong(Nat, Bool, z => Nat.is_le(Nat.add({TN('o')}, z), {TN('en')}), {TN(SH('m'))}, A.pow2(m), th), hl)
  %Equal.sym(Nat, {TN(f'(o + {SH("m")} : U32)')}, Nat.add({TN('o')}, {TN(SH('m'))}), A.u.tn_add(o, {SH('m')}, en, b)) :
    {le("Nat.add(_, A.pow2(m))", TN("en"))}
  %Equal.sym(Nat, {TN(SH('m'))}, A.pow2(m), th) :
    {le(f"Nat.add(Nat.add({TN('o')}, _), A.pow2(m))", TN("en"))}
  %Equal.sym(Nat, Nat.add(Nat.add({TN('o')}, A.pow2(m)), A.pow2(m)), Nat.add({TN('o')}, Nat.add(A.pow2(m), A.pow2(m))), A.add_assoc({TN('o')}, A.pow2(m), A.pow2(m))) :
    {le("_", TN("en"))}
  %A.double_add(A.pow2(m)) :
    {le(f"Nat.add({TN('o')}, _)", TN("en"))}
  h
'''


def halves():
    """tree1 over 2^(m+1) chunks is its two halves under a parent."""
    H, S = SH("m"), SH("1n+m")
    D = f"U32.sub({S}, {H})"
    rhs = f"B3.parent({T('m', f'B3.big(m, {H})', '(x, x)', 'c', H, '0')}, {T('m', f'B3.big(m, {H})', '(x, x)', f'(c + {H} : U32)', H, '0')}, rf)"
    goal = f"{{{T('1n+m', 'True{}', '(x, x)', 'c', S, 'rf')} == {rhs} : B3.CV}}"
    m1 = f"{{B3.parent({T('m', f'B3.big(m, {H})', '_', 'c', H, '0')}, {T('m', f'B3.big(m, {D})', '_', f'(c + {H} : U32)', D, '0')}, rf) == {rhs} : B3.CV}}"
    m2 = f"{{B3.parent({T('m', f'B3.big(m, {H})', '(x, x)', 'c', H, '0')}, {T('m', 'B3.big(m, _)', '(x, x)', f'(c + {H} : U32)', '_', '0')}, rf) == {rhs} : B3.CV}}"
    lines, bi = wmatch("r", ["z1"], "  ")
    body = (rw(bi, f"Equal.sym(Array<U32> & Array<U32>, {CLX}, (x, x), {CLONE.format(z='z1')})", m1) +
            rw(bi, f"Equal.sym(U32, {D}, {H}, A.sh.sub(m))", m2) + f"{bi}{{==}}\n")
    H1, S2 = SH("1n+m"), SH("2n+m")
    rhsT = f"B3.parent({T('1n+m', 'True{}', '(x, x)', 'c', H1, '0')}, {T('1n+m', 'True{}', '(x, x)', f'(c + {H1} : U32)', H1, '0')}, rf)"
    mT = f"{{{T('2n+m', 'True{}', '(x, x)', 'c', S2, 'rf')} == B3.parent({T('1n+m', '_', '(x, x)', 'c', H1, '0')}, {T('1n+m', '_', '(x, x)', f'(c + {H1} : U32)', H1, '0')}, rf) : B3.CV}}"
    return (f'''
# Halving the scalar tree
# -----------------------
''' + f"\ndef tree1.half.h(+m: Nat, -x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +rf: U32, r: Wits(x, 1n)) -> {goal}:\n" +
            "".join(lines) + body + f'''
# tree1 over 2^(m+1) chunks from c is a parent over its two halves.
law tree1.half:
  for +m: Nat
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {goal}

def tree1.half(m, x, c, cb, nch, last, rf):
  tree1.half.h(m, x, c, cb, nch, last, rf, wits(0n, x))

# The same with the halves' own split decided: 2^(m+1) > 2^m while it fits.
law tree1.halfT:
  for +m: Nat
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +em: {le("1n+m", "31n")}
  {{{T('2n+m', 'True{}', '(x, x)', 'c', S2, 'rf')} == {rhsT} : B3.CV}}

def tree1.halfT(m, x, c, cb, nch, last, rf, em):
  %A.sh.gt(m, em) :
    {mT}
  tree1.half(1n+m, x, c, cb, nch, last, rf)
''')


def quad_val():
    """quad(a, c, t, st) hands back four g16 CVs (g16.eta at each step)."""
    cs, ts = offs("c"), offs("t")
    S = lambda arr, i: sndc(f"B3.g16({arr}, {cs[i]}, {ts[i]}, 0)")
    Ss = [S("a", i) for i in range(4)]
    states = [f"B3.quad.s0(_, c, t, st)",
              f"B3.quad.s1(_, c, t, st, {Ss[0]})",
              f"B3.quad.s2(_, c, t, st, {Ss[0]}, {Ss[1]})",
              f"B3.quad.s3(_, {Ss[0]}, {Ss[1]}, {Ss[2]})"]
    val = f"B3.CV4{{{', '.join(Ss)}}}"
    lines, bi = wmatch("r", ["z0", "z1", "z2", "z3"], "  ")
    b = []
    for i in range(4):
        fact = (f"tr(arr => {{B3.g16(arr, {cs[i]}, {ts[i]}, 0) == (arr, {S('arr', i)}) : Array<U32> & B3.CV}}, "
                f"z{i}, a, ez{i}0, g16.eta(z{i}, {cs[i]}, {ts[i]}, 0))")
        b.append(rw(bi, f"Equal.sym(Array<U32> & B3.CV, B3.g16(a, {cs[i]}, {ts[i]}, 0), (a, {Ss[i]}), {fact})",
                    f"{{{states[i]} == {val} : B3.CV4}}"))
    b.append(f"{bi}{{==}}\n")
    goal = f"{{B3.quad(a, c, t, st) == {val} : B3.CV4}}"
    return (f'''
# Strided lanes
# -------------
''' + f"\ndef quad.val.h(-a: Array<U32>, +c: U32, +t: U32, +st: U32, r: Wits(a, 4n)) -> {goal}:\n" +
            "".join(lines) + "".join(b) + f'''
# A lane's four 16-chunk groups, st chunks apart.
law quad.val:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  for +st: U32
  {goal}

def quad.val(a, c, t, st):
  quad.val.h(a, c, t, st, wits(3n, a))
''')


def H(i, o):
    """Lane hypothesis i: group i's range (from o, 16 << r chunks long) ends
    by en."""
    return f"+h{i}: {le(f'Nat.add({TN(o)}, A.pow2(Nat.add(4n, r)))', TN('en'))}"


def quad_eq():
    """A lane is four scalar 16-chunk subtrees, where they are full."""
    os = offs("c")
    t = "(cb + c : U32)"
    ts = offs(t)
    V = lambda arr, i: sndc(f"B3.g16({arr}, {os[i]}, {ts[i]}, 0)")
    GF = lambda arr, o, tt: f"B3.g.fin(B3.g16({arr}, {o}, {tt}, 0))"
    T4 = lambda o, arr="x": T("4n", "True{}", f"({arr}, {arr})", o, "16", "0")
    R = f"B3.CV4{{{', '.join(T4(o) for o in os)}}}"
    goal = f"{{B3.quad(x, c, {t}, st) == {R} : B3.CV4}}"
    names = ["z0"] + [f"q{i}{w}" for i in range(4) for w in "ab"]
    lines, bi = wmatch("r", names, "  ")
    tr_ = lambda q, z, f: f"tr(arr => {q}, {z}, x, e{z}0, {f})"
    Vs = [V("x", i) for i in range(4)]
    qv = tr_(f"{{B3.quad(arr, c, {t}, st) == B3.CV4{{{', '.join(V('arr', i) for i in range(4))}}} : B3.CV4}}", "z0",
             f"quad.val(z0, c, {t}, st)")
    b = [rw(bi, f"Equal.sym(B3.CV4, B3.quad(x, c, {t}, st), B3.CV4{{{', '.join(Vs)}}}, {qv})", f"{{_ == {R} : B3.CV4}}")]
    cur = list(Vs)
    for i, o in enumerate(os):
        za, zb = f"q{i}a", f"q{i}b"
        inv = f"A.n.le_trans(Nat.add({TN(o)}, 16n), {TN('en')}, {TN('nch')}, h{i}, ee)"
        ef = f"sub.full({o}, 16, en, nch, last, ee, fe, h{i})"
        Q = tr_(f"{{{GF('arr', o, f'(cb + {o} : U32)')} == {T4(o, 'arr')} : B3.CV}}", za,
                f"g16.eq({za}, {o}, cb, nch, last, 0, {inv}, {ef})")
        G = tr_(f"{{{GF('arr', o, ts[i])} == {V('arr', i)} : B3.CV}}", zb, f"gfin.snd(B3.g16({zb}, {o}, {ts[i]}, 0))")
        if i == 0:
            Qp = Q
        else:
            idx = f"Equal.cong(U32, B3.CV, z => {GF('x', o, 'z')}, {ts[i]}, (cb + {o} : U32), A.u.add_assoc(cb, c, {X[i]}))"
            Qp = f"Equal.trans(B3.CV, {GF('x', o, ts[i])}, {GF('x', o, f'(cb + {o} : U32)')}, {T4(o)}, {idx}, {Q})"
        full = f"Equal.trans(B3.CV, {Vs[i]}, {GF('x', o, ts[i])}, {T4(o)}, Equal.sym(B3.CV, {GF('x', o, ts[i])}, {Vs[i]}, {G}), {Qp})"
        hole = list(cur)
        hole[i] = "_"
        b.append(rw(bi, f"Equal.sym(B3.CV, {Vs[i]}, {T4(o)}, {full})", f"{{B3.CV4{{{', '.join(hole)}}} == {R} : B3.CV4}}"))
        cur[i] = T4(o)
    b.append(f"{bi}{{==}}\n")
    hyps = [f"+h{i}: {le(f'Nat.add({TN(o)}, 16n)', TN('en'))}" for i, o in enumerate(os)]
    params = (f"-x: Array<U32>, +c: U32, +cb: U32, +nch: U32, +last: U32, +st: U32, +en: U32, "
              f"+ee: {le(TN('en'), TN('nch'))}, +fe: {{B3.full(en, nch, last) == True{{}} : Bool}}, " + ", ".join(hyps))
    fors = "".join(f"  for {h}\n" for h in hyps)
    return (f"\ndef quad.eq.h({params}, r: Wits(x, {len(names)}n)) -> {goal}:\n" + "".join(lines) + "".join(b) + f'''
# A lane is four scalar 16-chunk subtrees, where each ends inside a full range.
law quad.eq:
  for x: Array<U32>
  for +c: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +st: U32
  for +en: U32
  for +ee: {le(TN('en'), TN('nch'))}
  for +fe: {{B3.full(en, nch, last) == True{{}} : Bool}}
{fors}  {goal}

def quad.eq(x, c, cb, nch, last, st, en, ee, fe, h0, h1, h2, h3):
  quad.eq.h(x, c, cb, nch, last, st, en, ee, fe, h0, h1, h2, h3, wits({len(names) - 1}n, x))
''')


def qt():
    """2^r lanes from c are four scalar subtrees of 16 << r chunks, one per
    quarter: induction on r, each join a parent of its halves' groups."""
    K = lambda r: f"Nat.add(4n, {r})"
    TR = lambda r, o: T(K(r), "True{}", "(x, x)", o, SH(K(r)), "0")
    os = offs("c")
    goal = f"{{B3.qtree({TS}, r, (x, x), c, (cb + c : U32), st) == B3.CV4{{{', '.join(TR('r', o) for o in os)}}} : B3.CV4}}"
    hs = [H(i, o) for i, o in enumerate(os)]
    # The step: r = 1 + s, h = 16 << s, the right half's lanes from c + h.
    h = "U32.shln(16, s)"
    Hs = SH(K("s"))
    ch = f"(c + {h} : U32)"
    osr = offs(ch)
    Rs = f"B3.CV4{{{', '.join(TR('1n+s', o) for o in os)}}}"
    LQ = lambda aa1, aa2, t2: (f"B3.par4(B3.qtree({TS}, s, {aa1}, c, (cb + c : U32), st), "
                               f"B3.qtree({TS}, s, {aa2}, {ch}, {t2}, st))")
    zs = [f"z{i}" for i in range(1, 8)]
    l0, b0 = wmatch("w", zs, "      ")
    l1, ind = wmatch("w", zs, "      ")
    st_ = []
    st_.append(rw(ind, f"Equal.sym(Array<U32> & Array<U32>, {CLX}, (x, x), {CLONE.format(z='z1')})",
                  f"{{{LQ('_', '_', f'((cb + c : U32) + {h} : U32)')} == {Rs} : B3.CV4}}"))
    st_.append(rw(ind, f"Equal.sym(U32, ((cb + c : U32) + {h} : U32), (cb + {ch} : U32), A.u.add_assoc(cb, c, {h}))",
                  f"{{{LQ('(x, x)', '(x, x)', '_')} == {Rs} : B3.CV4}}"))
    ers = "A.le.succ_le(Nat.add(4n, s), 31n, er)"
    wl = "tr(arr => Wits(arr, 7n), z2, x, ez20, wits(6n, z2))"
    wr = "tr(arr => Wits(arr, 7n), z3, x, ez30, wits(6n, z3))"
    P = f"A.pow2({K('s')})"
    hl = [f"hyp.l({o}, {P}, en, h{i})" for i, o in enumerate(os)]
    # The right lanes' groups: o_i(c + h) is o_i(c) + 2^(4+s).
    eqo = [f"Equal.cong(U32, U32, z => (c + z : U32), {h}, {Hs}, A.sh16(s))"] + \
          [f"A.off.sh(c, {x}, s)" for x in X[1:]]
    sums = [f"({o} + {Hs} : U32)" for o in os]
    hr = [f"Equal.trans(Bool, Nat.is_le(Nat.add({TN(osr[i])}, {P}), {TN('en')}), Nat.is_le(Nat.add({TN(sums[i])}, {P}), {TN('en')}), True{{}}, "
          f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add(U32.to_nat(z), {P}), {TN('en')}), {osr[i]}, {sums[i]}, {eqo[i]}), "
          f"hyp.r({os[i]}, {K('s')}, en, {ers}, h{i}))" for i in range(4)]
    TS_ = lambda o: T(K("s"), "True{}", "(x, x)", o, Hs, "0")
    IHl = f"qt(s, x, {wl}, c, st, cb, nch, last, en, ee, fe, {ers}, {', '.join(hl)})"
    IHr = f"qt(s, x, {wr}, {ch}, st, cb, nch, last, en, ee, fe, {ers}, {', '.join(hr)})"
    L4 = f"B3.CV4{{{', '.join(TS_(o) for o in os)}}}"
    R4 = f"B3.CV4{{{', '.join(TS_(o) for o in osr)}}}"
    st_.append(rw(ind, f"Equal.sym(B3.CV4, B3.qtree({TS}, s, (x, x), c, (cb + c : U32), st), {L4}, {IHl})",
                  f"{{B3.par4(_, B3.qtree({TS}, s, (x, x), {ch}, (cb + {ch} : U32), st)) == {Rs} : B3.CV4}}"))
    st_.append(rw(ind, f"Equal.sym(B3.CV4, B3.qtree({TS}, s, (x, x), {ch}, (cb + {ch} : U32), st), {R4}, {IHr})",
                  f"{{B3.par4({L4}, _) == {Rs} : B3.CV4}}"))
    # Now par4 is four parents; split each quarter of the right side.
    lhs = f"B3.par4({L4}, {R4})"
    par = lambda o, o2: f"B3.parent({TS_(o)}, {TS_(o2)}, 0)"
    cur = [TR("1n+s", o) for o in os]
    m = "Nat.add(3n, s)"
    for i, o in enumerate(os):
        z = f"z{4 + i}"
        H1 = SH(f"1n+{m}")
        halfT = (f"tr(arr => {{{T(f'2n+{m}', 'True{}', '(arr, arr)', o, SH(f'2n+{m}'), '0')} == "
                 f"B3.parent({T(f'1n+{m}', 'True{}', '(arr, arr)', o, H1, '0')}, {T(f'1n+{m}', 'True{}', '(arr, arr)', f'({o} + {H1} : U32)', H1, '0')}, 0) : B3.CV}}, "
                 f"{z}, x, e{z}0, tree1.halfT({m}, {z}, {o}, cb, nch, last, 0, {ers}))")
        new = par(o, sums[i])
        hole = list(cur)
        hole[i] = "_"
        st_.append(rw(ind, f"Equal.sym(B3.CV, {TR('1n+s', o)}, {new}, {halfT})",
                      f"{{{lhs} == B3.CV4{{{', '.join(hole)}}} : B3.CV4}}"))
        cur[i] = new
    for i, o in enumerate(os):
        hole = list(cur)
        hole[i] = f"B3.parent({TS_(o)}, {TS_('_')}, 0)"
        st_.append(rw(ind, eqo[i], f"{{{lhs} == B3.CV4{{{', '.join(hole)}}} : B3.CV4}}"))
        cur[i] = par(o, osr[i])
    st_.append(f"{ind}{{==}}\n")
    base = (f"{b0}{'; '.join(f'_ = {z}' for z in zs[1:])}\n".replace("; ", f"\n{b0}") +
            f"{b0}tr(arr => {{B3.quad(arr, c, (cb + c : U32), st) == B3.CV4{{{', '.join(T('4n', 'True{}', '(arr, arr)', o, '16', '0') for o in os)}}} : B3.CV4}}, "
            f"z1, x, ez10, quad.eq(z1, c, cb, nch, last, st, en, ee, fe, h0, h1, h2, h3))\n")
    fors = "".join(f"  for {h_}\n" for h_ in hs)
    return f'''
# 2^r lanes from c (lane j at c + 16j) are four scalar subtrees of 16 << r
# chunks, from c, c + st, c + 2st and c + 3st: at r = 0 a lane's groups, and
# a join pairs its halves' groups into the next level's subtrees.
law qt:
  for +r: Nat
  for -x: Array<U32>
  for w: Wits(x, 7n)
  for +c: U32
  for +st: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +en: U32
  for +ee: {le(TN('en'), TN('nch'))}
  for +fe: {{B3.full(en, nch, last) == True{{}} : Bool}}
  for +er: {le("Nat.add(4n, r)", "31n")}
{fors}  {goal}

def qt(r, x, w, c, st, cb, nch, last, en, ee, fe, er, h0, h1, h2, h3):
  match r:
    case 0n:
''' + "".join(l0) + base + "    case 1n+s:\n" + "".join(l1) + "".join(st_)


def text():
    return ranges() + halves() + quad_val() + quad_eq() + qt()
