"""The 8-lane chunk loop, lane by lane: loop.l<l> proves that lane l of c8.go
(eight chunks, sixteen blocks, compress8) is the scalar chunk.go of chunk l,
for every array, by induction on the blocks left."""
from .common import L, CE, WL, snd8, fst8, sndm, ldx, X

NW = 11  # array copies a level of the induction spends


def loaders():
    allX = lambda a, w: ", ".join(X(a, w, j) for j in range(L))
    out = [f'''
# The 8-lane loader hands its array back.
law ld8.fst:
  for a: Array<U32>
  for +w: U32
  {{{fst8("B3.ld8(a, w)")} == a : Array<U32>}}

def ld8.fst(a, w):
  Equal.cong(Array<U32> & B3.B128, Array<U32>, p => {fst8("p")}, B3.ld8(a, w), (a, B3.b128.of({allX("a", "w")})), ld8.words(a, w))

law ld8.eta:
  for a: Array<U32>
  for +w: U32
  {{B3.ld8(a, w) == (a, {snd8("B3.ld8(a, w)")}) : Array<U32> & B3.B128}}

def ld8.eta(a, w):
  %Equal.sym(Array<U32> & B3.B128, B3.ld8(a, w), (a, B3.b128.of({allX("a", "w")})), ld8.words(a, w)) :
    {{_ == (a, Pair.snd(Array<U32>, B3.B128, _)) : Array<U32> & B3.B128}}
  {{==}}

# Its block, with each lane's block named by a copy of a.
''']
    ys = [f"y{j}" for j in range(L)]
    eys = [f"ey{j}" for j in range(L)]
    stmt = f"{{{snd8('B3.ld8(a, w)')} == B3.b128.of({', '.join(X(y, 'w', j) for j, y in enumerate(ys))}) : B3.B128}}"
    # From ld8.words on z: rewrite each field's array y_j to z, then a to z.
    base = (f"Equal.cong(Array<U32> & B3.B128, B3.B128, p => {snd8('p')}, B3.ld8(z, w), "
            f"(z, B3.b128.of({allX('z', 'w')})), ld8.words(z, w))")
    proof = []
    for j in range(L):
        fields = ", ".join(("_" if k == j else (X("z", "w", k) if k < j else X(ys[k], "w", k))) for k in range(L))
        mot = f"{{{snd8('B3.ld8(a, w)')} == B3.b128.of({fields}) : B3.B128}}"
        e = (f"Equal.cong(Array<U32>, B3.M16, c => {X('c', 'w', j)}, z, {ys[j]}, "
             f"eq.trans(z, a, {ys[j]}, ez, Equal.sym(Array<U32>, {ys[j]}, a, {eys[j]})))")
        proof.append(f"  %{e} :\n    {mot}\n")
    proof.append(f"  %Equal.cong(Array<U32>, B3.B128, c => {snd8('B3.ld8(c, w)')}, z, a, ez) :\n"
                 f"    {{_ == B3.b128.of({allX('z', 'w')}) : B3.B128}}\n")
    proof.append(f"  {base}\n")
    out.append("law ld8.split:\n  for -a: Array<U32>\n  for +w: U32\n  for z: Array<U32>\n"
               "  for +ez: {z == a : Array<U32>}\n" +
               "".join(f"  for -{y}: Array<U32>\n  for +{e}: {{{y} == a : Array<U32>}}\n" for y, e in zip(ys, eys)) +
               f"  {stmt}\n\n"
               f"def ld8.split(a, w, z, ez, {', '.join(f'{y}, {e}' for y, e in zip(ys, eys))}):\n" + "".join(proof))
    return "".join(out)


def bundles():
    return f'''
# A level's copies, and one level per block left.
def Bun(-a: Array<U32>, p: Nat) -> Type:
  match p:
    case 0n:
      Unit
    case 1n+q:
      Wits(a, {NW}n) & Bun(a, q)

def BunS(-a: Array<U32>, p: Nat) -> Type:
  Exists(Array<U32>, s => {{s == a : Array<U32>}} & Bun(a, p))

def bun.add2(-a: Array<U32>, +q: Nat, -s: Array<U32>, +es: {{s == a : Array<U32>}}, w: Wits(s, {NW + 1}n), rest: Bun(a, q)) -> BunS(a, 1n+q):
  match w:
    case (s2, w2):
      match w2:
        case (es2, lvl):
          (s2, (eq.trans(s2, s, a, es2, es), (tr(c => Wits(c, {NW}n), s, a, es, lvl), rest)))

def bun.add(-a: Array<U32>, +q: Nat, r: BunS(a, q)) -> BunS(a, 1n+q):
  match r:
    case (s, r2):
      match r2:
        case (es, rest):
          bun.add2(a, q, s, es, wits({NW}n, s), rest)

law bun:
  for +p: Nat
  for a: Array<U32>
  BunS(a, p)

def bun(p, a):
  match p:
    case 0n:
      (a, ({{==}}, Unit{{}}))
    case 1n+q:
      bun.add(a, q, bun(q, a))

# (w + 16) + k is (w + k) + 16.
law swap16:
  for +w: U32
  for +k: U32
  {{((w + 16 : U32) + k : U32) == ((w + k : U32) + 16 : U32) : U32}}

def swap16(w, k):
  %Equal.sym(U32, U32.add(U32.add(w, 16), k), U32.add(w, U32.add(16, k)), A.u.add_assoc(w, 16, k)) : {{_ == ((w + k : U32) + 16 : U32) : U32}}
  %U32.add_comm(k, 16) : {{U32.add(w, _) == ((w + k : U32) + 16 : U32) : U32}}
  Equal.sym(U32, ((w + k : U32) + 16 : U32), U32.add(w, U32.add(k, 16)), A.u.add_assoc(w, k, 16))
'''


def loop(l):
    Ll = f"L{l}{{}}"
    ms = [f"m{j}" for j in range(L)]
    msa = ", ".join(ms)
    lhs = lambda n, r, w, cv, ctr, fl: f"cv.at({Ll}, Pair.snd(Array<U32>, B3.CV8, B3.c8.go({n}, {r}, {w}, {cv}, {ctr}, {fl})))"
    rhs = lambda p, arr, mm, w, cvl, ctr, fl: (f"B3.chunk.fin(B3.chunk.go({p}, ({arr}, {mm}), {WL(l, w)}, {cvl}, "
                                              f"({ctr} + {l} : U32), {fl}, {CE}, 64))")
    head = (f"\n# Lane {l} of the 8-lane loop is the scalar loop of chunk {l}.\n"
            f"law loop.l{l}:\n  for +p: Nat\n  for -a0: Array<U32>\n  for r: Array<U32> & B3.B128\n"
            f"  for +er: {{{fst8('r')} == a0 : Array<U32>}}\n" +
            "".join(f"  for +{m}: B3.M16\n" for m in ms) +
            f"  for +em: {{{snd8('r')} == B3.b128.of({msa}) : B3.B128}}\n"
            "  for +w: U32\n  for +cv: B3.CV8\n  for +ctr: U32\n  for +fl: U32\n  for bun: Bun(a0, p)\n"
            f"  {{{lhs('1n+p', 'r', 'w', 'cv', 'ctr', 'fl')} ==\n"
            f"    {rhs('p', 'a0', f'm{l}', 'w', f'cv.at({Ll}, cv)', 'ctr', 'fl')} : B3.CV}}\n")
    c8l = lambda F: (f"Equal.sym(B3.CV, cv.at({Ll}, B3.compress8(cv, m, ctr, 1, 64, {F})), "
                     f"B3.compress(cv.at({Ll}, cv), m.at({Ll}, m), (ctr + {l} : U32), 0, 64, {F}), "
                     f"compress8.lane({Ll}, cv, m, ctr, 1, 64, {F}))")
    pick = f"Equal.sym(B3.M16, m.at({Ll}, B3.b128.of({msa})), m.pick({Ll}, {msa}), b128.lane({Ll}, {msa}))"
    # The last block: one compress8, then the loop stops.
    fl0 = f"(fl .|. {CE} : U32)"
    rhs0 = rhs("0n", "a0", f"m{l}", "w", f"cv.at({Ll}, cv)", "ctr", "fl")
    i0 = "          "
    case0 = (f"    case 0n:\n      match r:\n        case (a, +m):\n"
             f"{i0}_ = bun\n"
             f"{i0}%Equal.sym(Array<U32> & B3.B128, B3.ld8(a, (w + 0 : U32)), (a, {snd8('B3.ld8(a, (w + 0 : U32))')}), ld8.eta(a, (w + 0 : U32))) :\n"
             f"{i0}  {{cv.at({Ll}, Pair.snd(Array<U32>, B3.CV8, B3.c8.go(0n, _, (w + 0 : U32), B3.compress8(cv, m, ctr, 1, 64, {fl0}), ctr, 0))) == {rhs0} : B3.CV}}\n"
             f"{i0}%{c8l(fl0)} :\n{i0}  {{_ == {rhs0} : B3.CV}}\n"
             f"{i0}%Equal.sym(B3.B128, m, B3.b128.of({msa}), em) :\n"
             f"{i0}  {{B3.compress(cv.at({Ll}, cv), m.at({Ll}, _), (ctr + {l} : U32), 0, 64, {fl0}) == {rhs0} : B3.CV}}\n"
             f"{i0}%{pick} :\n{i0}  {{B3.compress(cv.at({Ll}, cv), _, (ctr + {l} : U32), 0, 64, {fl0}) == {rhs0} : B3.CV}}\n"
             f"{i0}{{==}}\n")
    # A block more: the level's copies x1..x11.
    xs = [f"x{i}" for i in range(1, NW + 1)]
    lines = []
    ind = "              "
    lines.append(f"{ind}match lvl:\n")
    for i, x in enumerate(xs, 1):
        lines.append(f"{ind}  case ({x}, w{i}):\n")
        lines.append(f"{ind}    match w{i}:\n")
        lines.append(f"{ind}      case (+e{i}, w{i}b):\n")
        ind = ind + "        "
        lines.append(f"{ind}match w{i}b:\n" if i < NW else f"{ind}_ = w{i}b\n")
    bi = ind
    w16 = "(w + 16 : U32)"
    Mp = [f"mm{j}" for j in range(L)]
    sym_ea = "Equal.sym(Array<U32>, a, a0, ea)"
    b = [f"{bi}+ea = er\n"]
    # x1..x8 name the next block's lanes, x9 proves them, x10 hands the
    # array back, x11 loads the scalar side's block.
    for j in range(L):
        b.append(f"{bi}+{Mp[j]} = {sndm(ldx(xs[j], WL(j, w16)))}\n")
    split_args = ", ".join(f"{xs[j]}, eq.trans({xs[j]}, a0, a, e{j + 1}, {sym_ea})" for j in range(L))
    b.append(f"{bi}+em2 = ld8.split(a, {w16}, {xs[8]}, eq.trans({xs[8]}, a0, a, e9, {sym_ea}), {split_args})\n")
    b.append(f"{bi}+f3 = eq.trans({fst8('B3.ld8(a, ' + w16 + ')')}, a, a0, tr(c => {{{fst8('B3.ld8(c, ' + w16 + ')')} == c : Array<U32>}}, {xs[9]}, a, "
             f"eq.trans({xs[9]}, a0, a, e10, {sym_ea}), ld8.fst({xs[9]}, {w16})), ea)\n")
    C8 = "B3.compress8(cv, m, ctr, 1, 64, (fl .|. 0 : U32))"
    b.append(f"{bi}+ih = loop.l{l}(q, a0, B3.ld8(a, {w16}), f3, {', '.join(Mp)}, em2, {w16}, {C8}, ctr, 0, rest)\n")
    ihl = lhs("1n+q", f"B3.ld8(a, {w16})", w16, C8, "ctr", "0")
    ihr = rhs("q", "a0", Mp[l], w16, f"cv.at({Ll}, {C8})", "ctr", "0")
    I = f"({WL(l, 'w')} + 16 : U32)"
    goal_r = lambda hole: (f"B3.chunk.fin(B3.chunk.go(q, {hole}, {I}, B3.compress(cv.at({Ll}, cv), m{l}, (ctr + {l} : U32), 0, 64, fl), "
                           f"(ctr + {l} : U32), 0, {CE}, 64))")
    b.append(f"{bi}%Equal.sym(B3.CV, {ihl}, {ihr}, ih) :\n{bi}  {{_ == {goal_r(ldx('a0', I))} : B3.CV}}\n")
    f2 = f"tr(c => {{B3.ld(c, {I}) == (c, {sndm(ldx('c', I))}) : Array<U32> & B3.M16}}, {xs[10]}, a0, e11, ld.eta({xs[10]}, {I}))"
    b.append(f"{bi}%Equal.sym(Array<U32> & B3.M16, {ldx('a0', I)}, (a0, {sndm(ldx('a0', I))}), {f2}) :\n"
             f"{bi}  {{{ihr} == {goal_r('_')} : B3.CV}}\n")
    goalR = goal_r(f"(a0, {sndm(ldx('a0', I))})")
    nxt = sndm(ldx('a0', WL(l, w16)))
    b.append(f"{bi}%Equal.cong(Array<U32>, B3.M16, c => {sndm(ldx('c', WL(l, w16)))}, a0, {xs[l]}, Equal.sym(Array<U32>, {xs[l]}, a0, e{l + 1})) :\n"
             f"{bi}  {{{rhs('q', 'a0', '_', w16, f'cv.at({Ll}, {C8})', 'ctr', '0')} == {goalR} : B3.CV}}\n")
    b.append(f"{bi}%{c8l('(fl .|. 0 : U32)')} :\n{bi}  {{{rhs('q', 'a0', nxt, w16, '_', 'ctr', '0')} == {goalR} : B3.CV}}\n")
    cvl = lambda m_, f_: f"B3.compress(cv.at({Ll}, cv), {m_}, (ctr + {l} : U32), 0, 64, {f_})"
    b.append(f"{bi}%Equal.sym(B3.B128, m, B3.b128.of({msa}), em) :\n"
             f"{bi}  {{{rhs('q', 'a0', nxt, w16, cvl(f'm.at({Ll}, _)', '(fl .|. 0 : U32)'), 'ctr', '0')} == {goalR} : B3.CV}}\n")
    b.append(f"{bi}%{pick} :\n{bi}  {{{rhs('q', 'a0', nxt, w16, cvl('_', '(fl .|. 0 : U32)'), 'ctr', '0')} == {goalR} : B3.CV}}\n")
    b.append(f"{bi}%Equal.sym(U32, (fl .|. 0 : U32), fl, A.u.or_zero(fl)) :\n"
             f"{bi}  {{{rhs('q', 'a0', nxt, w16, cvl(f'm{l}', '_'), 'ctr', '0')} == {goalR} : B3.CV}}\n")
    if l > 0:
        K = 256 * l
        hole_r = (f"B3.chunk.fin(B3.chunk.go(q, (a0, {sndm(ldx('a0', '_'))}), _, {cvl(f'm{l}', 'fl')}, "
                  f"(ctr + {l} : U32), 0, {CE}, 64))")
        b.append(f"{bi}%Equal.sym(U32, ((w + 16 : U32) + {K} : U32), ((w + {K} : U32) + 16 : U32), swap16(w, {K})) :\n"
                 f"{bi}  {{{hole_r} == {goalR} : B3.CV}}\n")
    b.append(f"{bi}{{==}}\n")
    case1 = ("    case 1n+q:\n      match r:\n        case (a, +m):\n          match bun:\n            case (lvl, rest):\n" +
             "".join(lines) + "".join(b))
    return head + f"\ndef loop.l{l}(p, a0, r, er, {msa}, em, w, cv, ctr, fl, bun):\n  match p:\n" + case0 + case1


def text():
    return loaders() + bundles() + "".join(loop(l) for l in range(L))
