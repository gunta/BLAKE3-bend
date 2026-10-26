"""The CPU tree: cpu.tree proves tree8 is tree1 node for node (tree8's kind,
computed from a U32 copy of the depth, splits where tree1 does, and its
leaves are leaf8.eq and leaf32.eq), and cpu.at closes the entry point with
the depth bound (a span's tree is at most 32 deep)."""
from .common import TN

TS = "~share"
CL = "Array.clone(U32, x)"
I = "                          "
K1 = "1n+p"
KP = "(ku - 1 : U32)"


def T8(k, ku, d, aa, c, n, rf):
    return f"B3.tree8({TS}, {k}, {ku}, {d}, {aa}, {c}, {n}, cb, nch, last, {rf})"


def T1(k, b, aa, c, n, rf):
    return f"B3.tree1({TS}, {k}, {b}, {aa}, {c}, {n}, cb, nch, last, {rf})"


def KIND(ku, n, c):
    return f"B3.kind({ku}, {n}, {c}, nch, last)"


def F(ku, n, c):
    """kind's test for a whole, full node of depth ku over n chunks from c."""
    return f"(U32.is_eq({n}, U32.shln(1, U32.to_nat({ku}))) && B3.full(({c} + {n} : U32), nch, last))"


def helpers():
    return f'''
# At depth 0 both trees hash the one chunk, whatever kind tree8 was handed.
law t8.zero:
  for +ku: U32
  for d: B3.Node
  for -a1: Array<U32>
  for -a2: Array<U32>
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {{{T8("0n", "ku", "d", "(a1, a2)", "c", "n", "rf")} == {T1("0n", "False{}", "(a1, a2)", "c", "n", "rf")} : B3.CV}}

def t8.zero(ku, d, a1, a2, c, n, cb, nch, last, rf):
  match d:
    case B3.Down{{}}:
      {{==}}
    case B3.Split{{}}:
      {{==}}
    case B3.Leaf8{{}}:
      {{==}}
    case B3.Leaf32{{}}:
      {{==}}

def pred(n: Nat) -> Nat:
  match n:
    case 0n:
      0n
    case 1n+p:
      p

# The right child of a split keeps c + n <= nch.
law inv.split:
  for +c: U32
  for +n: U32
  for +h: U32
  for +nch: U32
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, {TN("n")}), {TN("nch")}) == True{{}} : Bool}}
  for +lt: {{Nat.is_lt({TN("h")}, {TN("n")}) == True{{}} : Bool}}
  {{Nat.is_le(Nat.add({TN("(c + h : U32)")}, {TN("(n - h : U32)")}), {TN("nch")}) == True{{}} : Bool}}

def inv.split(c, n, h, nch, inv, lt):
  +C = {TN("c")}
  +N = {TN("n")}
  +H = {TN("h")}
  +le_h = A.n.lt_to_le(H, N, lt)
  +inv_l = A.n.le_trans(Nat.add(C, H), Nat.add(C, N), {TN("nch")}, A.n.add_le(C, H, N, le_h), inv)
  %Equal.sym(Nat, {TN("(c + h : U32)")}, Nat.add(C, H), A.u.tn_add(c, h, nch, inv_l)) : {{Nat.is_le(Nat.add(_, {TN("(n - h : U32)")}), {TN("nch")}) == True{{}} : Bool}}
  %Equal.sym(Nat, {TN("(n - h : U32)")}, Nat.sub(N, H), A.u.tn_sub(n, h, le_h)) : {{Nat.is_le(Nat.add(Nat.add(C, H), _), {TN("nch")}) == True{{}} : Bool}}
  %Equal.sym(Nat, Nat.add(Nat.add(C, H), Nat.sub(N, H)), Nat.add(C, Nat.add(H, Nat.sub(N, H))), A.add_assoc(C, H, Nat.sub(N, H))) : {{Nat.is_le(_, {TN("nch")}) == True{{}} : Bool}}
  %Equal.sym(Nat, Nat.add(H, Nat.sub(N, H)), N, A.n.add_sub(H, N, le_h)) : {{Nat.is_le(Nat.add(C, _), {TN("nch")}) == True{{}} : Bool}}
  inv

# The left child keeps it too.
law inv.left:
  for +c: U32
  for +n: U32
  for +h: U32
  for +nch: U32
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, {TN("n")}), {TN("nch")}) == True{{}} : Bool}}
  for +lt: {{Nat.is_lt({TN("h")}, {TN("n")}) == True{{}} : Bool}}
  {{Nat.is_le(Nat.add({TN("c")}, {TN("h")}), {TN("nch")}) == True{{}} : Bool}}

def inv.left(c, n, h, nch, inv, lt):
  A.n.le_trans(Nat.add({TN("c")}, {TN("h")}), Nat.add({TN("c")}, {TN("n")}), {TN("nch")}, A.n.add_le({TN("c")}, {TN("h")}, {TN("n")}, A.n.lt_to_le({TN("h")}, {TN("n")}, lt)), inv)

# The node's depth, from its U32 copy: 1 + p is ku's value.
law k.val:
  for +p: Nat
  for +ku: U32
  for +j: U32
  for +eku: {{ku == U32.from_nat(1n+p) : U32}}
  for +ek: {{Nat.is_le(1n+p, 32n) == True{{}} : Bool}}
  for +ej: {{ku == j : U32}}
  {{1n+p == {TN("j")} : Nat}}

def k.val(p, ku, j, eku, ek, ej):
  Equal.trans(Nat, 1n+p, {TN("ku")}, {TN("j")},
    Equal.trans(Nat, 1n+p, {TN("U32.from_nat(1n+p)")}, {TN("ku")}, Equal.sym(Nat, {TN("U32.from_nat(1n+p)")}, 1n+p, A.u.tn_fn(1n+p, 32, ek)),
      Equal.cong(U32, Nat, z => U32.to_nat(z), U32.from_nat(1n+p), ku, Equal.sym(U32, ku, U32.from_nat(1n+p), eku))),
    Equal.cong(U32, Nat, z => U32.to_nat(z), ku, j, ej))
'''


def kb(arg):
    return f"B3.kind.big(ku, n, c, nch, last, {arg})"


def rewrite(eq, val, ty, motive_kind):
    """Rewrites a decision of the node (its equation eq) to the matched value."""
    return (f"{I}%Equal.sym({ty}, {eq[0]}, {val}, {eq[1]}) :\n"
            f"{I}  {{{T8(K1, 'ku', motive_kind, CL, 'c', 'n', 'rf')} == {T1(K1, 'True{}', CL, 'c', 'n', 'rf')} : B3.CV}}\n")


def node_cases():
    goal_rhs = T1(K1, "B3.big(1n+p, n)", CL, "c", "n", "rf")
    common = [
        f"{I}+ekp = A.le.succ_le(p, 32n, ek)\n",
        f"{I}+kd = Equal.trans(U32, {KP}, (U32.from_nat(1n+p) - 1 : U32), U32.from_nat(p), "
        f"Equal.cong(U32, U32, z => (z - 1 : U32), ku, U32.from_nat(1n+p), eku), A.u.down(p))\n",
        f"{I}+tp = Equal.trans(Nat, {TN(KP)}, {TN('U32.from_nat(p)')}, p, "
        f"Equal.cong(U32, Nat, z => U32.to_nat(z), {KP}, U32.from_nat(p), kd), A.u.tn_fn(p, 32, ekp))\n",
        f"{I}%Equal.sym(Nat, {TN(KP)}, p, tp) :\n"
        f"{I}  {{{T8(K1, 'ku', kb('U32.is_gt(n, U32.shln(1, _))'), CL, 'c', 'n', 'rf')} == {goal_rhs} : B3.CV}}\n",
    ]

    def r2(val):
        return (f"{I}%Equal.sym(Bool, B3.big(1n+p, n), {val}, eb) :\n"
                f"{I}  {{{T8(K1, 'ku', kb('_'), CL, 'c', 'n', 'rf')} == {T1(K1, '_', CL, 'c', 'n', 'rf')} : B3.CV}}\n")
    r3 = lambda val: rewrite((F("ku", "n", "c"), "ef"), val, "Bool", "B3.kind.full(ku, _)")
    r5 = lambda val: rewrite(("U32.is_eq(ku, 5)", "ee5"), val, "Bool", "B3.kind.at(_, ku)")
    r6 = lambda val: rewrite(("U32.is_eq(ku, 3)", "ee3"), val, "Bool", "B3.kind.at3(_)")

    def rclone(node):
        return (f"{I}%Equal.sym(Array<U32> & Array<U32>, {CL}, (x, x), ecl) :\n"
                f"{I}  {{{T8(K1, 'ku', node, '_', 'c', 'n', 'rf')} == {T1(K1, 'True{}', '_', 'c', 'n', 'rf')} : B3.CV}}\n")

    def ih(c, n, rf, pkx, inv):
        return (f"cpu.tree(p, x, {pkx}, {KP}, kd, ekp, {c}, {n}, cb, nch, last, {rf}, {inv}, B3.big(p, {n}), {{==}}, {F(KP, n, c)}, {{==}}, "
                f"U32.is_eq({KP}, 5), {{==}}, U32.is_eq({KP}, 3), {{==}})")

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
        t8l = T8("p", KP, KIND(KP, h, "c"), CL, "c", h, "0")
        t8r = T8("p", KP, KIND(KP, n2, c2), CL, c2, n2, "0")
        t1l = T1("p", f"B3.big(p, {h})", CL, "c", h, "0")
        t1r = T1("p", f"B3.big(p, {n2})", CL, c2, n2, "0")
        rhs = f"B3.parent({t1l}, {t1r}, rf)"
        return [f"{I}+lt = A.n.gt_lt({TN('n')}, {TN(h)}, {gt})\n",
                f"{I}%Equal.sym(B3.CV, {t8l}, {t1l}, {ihl}) :\n{I}  {{B3.parent(_, {t8r}, rf) == {rhs} : B3.CV}}\n",
                f"{I}%Equal.sym(B3.CV, {t8r}, {t1r}, {ihr}) :\n{I}  {{B3.parent({t1l}, _, rf) == {rhs} : B3.CV}}\n",
                f"{I}{{==}}\n"]

    def leaf(kv, nv):
        # A whole, full node of depth kv (5 or 3) over nv chunks (32 or 8).
        s = [f"{I}+kq = A.u.eq_sound(ku, {kv}, {'ee5' if kv == 5 else 'ee3'})\n",
             f"{I}+pv = Equal.cong(Nat, Nat, z => pred(z), 1n+p, {kv}n, k.val(p, ku, {kv}, eku, ek, kq))\n",
             f"{I}+fk = Equal.trans(Bool, {F(str(kv), 'n', 'c')}, {F('ku', 'n', 'c')}, True{{}}, "
             f"Equal.cong(U32, Bool, z => {F('z', 'n', 'c')}, {kv}, ku, Equal.sym(U32, ku, {kv}, kq)), ef)\n",
             f"{I}+nq = A.u.eq_sound(n, {nv}, A.and.l(U32.is_eq(n, {nv}), B3.full((c + n : U32), nch, last), fk))\n",
             f"{I}+efull = A.and.r(U32.is_eq(n, {nv}), B3.full((c + n : U32), nch, last), fk)\n",
             f"{I}+invk = Equal.trans(Bool, Nat.is_le(Nat.add({TN('c')}, {nv}n), {TN('nch')}), Nat.is_le(Nat.add({TN('c')}, {TN('n')}), {TN('nch')}), True{{}}, "
             f"Equal.cong(U32, Bool, z => Nat.is_le(Nat.add({TN('c')}, U32.to_nat(z)), {TN('nch')}), {nv}, n, Equal.sym(U32, n, {nv}, nq)), inv)\n",
             f"{I}+efk = Equal.trans(Bool, B3.full((c + {nv} : U32), nch, last), B3.full((c + n : U32), nch, last), True{{}}, "
             f"Equal.cong(U32, Bool, z => B3.full((c + z : U32), nch, last), {nv}, n, Equal.sym(U32, n, {nv}, nq)), efull)\n"]
        lhs = "B3.leaf32(x, c, (cb + c : U32), rf)" if kv == 5 else "B3.leaf8(x, c, (cb + c : U32), rf)"
        s.append(f"{I}%Equal.sym(Nat, p, {kv - 1}n, pv) :\n{I}  {{{lhs} == {T1('1n+_', 'True{}', '(x, x)', 'c', 'n', 'rf')} : B3.CV}}\n")
        s.append(f"{I}%Equal.sym(U32, n, {nv}, nq) :\n{I}  {{{lhs} == {T1(f'{kv}n', 'True{}', '(x, x)', 'c', '_', 'rf')} : B3.CV}}\n")
        if kv == 5:
            s.append(f"{I}_ = x2\n")
            s.append(f"{I}tr(arr => {{B3.leaf32(arr, c, (cb + c : U32), rf) == {T1('5n', 'True{}', '(arr, arr)', 'c', '32', 'rf')} : B3.CV}}, "
                     f"x1, x, e1, leaf32.eq(x1, c, cb, nch, last, rf, invk, efk))\n")
        else:
            s.append(f"{I}leaf8.eq(x, x1, e1, x2, e2, c, cb, nch, last, rf, invk, efk)\n")
        return s

    split = common + [r2("True{}"), r3("False{}"), rclone("B3.Split{}")] + split_tail()
    split2 = common + [r2("True{}"), r3("True{}"), r5("False{}"), r6("False{}"), rclone("B3.Split{}")] + split_tail()
    leaf32c = common + [r2("True{}"), r3("True{}"), r5("True{}"), rclone("B3.Leaf32{}")] + leaf(5, 32)
    leaf8c = common + [r2("True{}"), r3("True{}"), r5("False{}"), r6("True{}"), rclone("B3.Leaf8{}")] + leaf(3, 8)
    c = "                        case "
    return (f"{c}False{{}} _ _ _:\n" + "".join(down) +
            f"{c}True{{}} False{{}} _ _:\n" + "".join(split) +
            f"{c}True{{}} True{{}} True{{}} _:\n" + "".join(leaf32c) +
            f"{c}True{{}} True{{}} False{{}} True{{}}:\n" + "".join(leaf8c) +
            f"{c}True{{}} True{{}} False{{}} False{{}}:\n" + "".join(split2))


def cpu_tree():
    open_pk = '''      match pk:
        case (x1, pk2):
          match pk2:
            case (x2, pk3):
              match pk3:
                case (+e1, pk4):
                  match pk4:
                    case (+e2, ecl):
'''
    return f'''
# The CPU tree is the scalar tree, node for node: tree8's kind (computed
# from ku, a U32 copy of the depth) takes tree1's split exactly where tree1
# does, and its 8- and 32-chunk leaves are the scalar subtrees (leaf8.eq,
# leaf32.eq). Each node holds a clone of x and two live copies of it (pk).
law cpu.tree:
  for +k: Nat
  for -x: Array<U32>
  for pk: CloneW(x)
  for +ku: U32
  for +eku: {{ku == U32.from_nat(k) : U32}}
  for +ek: {{Nat.is_le(k, 32n) == True{{}} : Bool}}
  for +c: U32
  for +n: U32
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +inv: {{Nat.is_le(Nat.add({TN("c")}, {TN("n")}), {TN("nch")}) == True{{}} : Bool}}
  for b: Bool
  for +eb: {{B3.big(k, n) == b : Bool}}
  for f: Bool
  for +ef: {{{F("ku", "n", "c")} == f : Bool}}
  for e5: Bool
  for +ee5: {{U32.is_eq(ku, 5) == e5 : Bool}}
  for e3: Bool
  for +ee3: {{U32.is_eq(ku, 3) == e3 : Bool}}
  {{{T8("k", "ku", KIND("ku", "n", "c"), CL, "c", "n", "rf")} ==
    {T1("k", "B3.big(k, n)", CL, "c", "n", "rf")} : B3.CV}}

def cpu.tree(k, x, pk, ku, eku, ek, c, n, cb, nch, last, rf, inv, b, eb, f, ef, e5, ee5, e3, ee3):
  match k:
    case 0n:
{open_pk}                      _ = x1
                      _ = x2
                      %Equal.sym(Array<U32> & Array<U32>, {CL}, (x, x), ecl) :
                        {{{T8("0n", "ku", KIND("ku", "n", "c"), "_", "c", "n", "rf")} == {T1("0n", "B3.big(0n, n)", "_", "c", "n", "rf")} : B3.CV}}
                      t8.zero(ku, {KIND("ku", "n", "c")}, x, x, c, n, cb, nch, last, rf)
    case 1n+p:
{open_pk}                      match b f e5 e3:
''' + node_cases()


def top():
    return f'''
# The depth is at most 32
# -----------------------

law n.mul_zero:
  for +s: Nat
  {{Nat.mul(s, 0n) == 0n : Nat}}

def n.mul_zero(s):
  match s:
    case 0n:
      {{==}}
    case 1n+p:
      n.mul_zero(p)

law n.mul_one:
  for +s: Nat
  {{Nat.mul(s, 1n) == s : Nat}}

def n.mul_one(s):
  match s:
    case 0n:
      {{==}}
    case 1n+p:
      Equal.cong(Nat, Nat, z => 1n+z, Nat.mul(p, 1n), p, n.mul_one(p))

law n.le_zero:
  for +s: Nat
  {{Nat.is_le(0n, s) == True{{}} : Bool}}

def n.le_zero(s):
  match s:
    case 0n:
      {{==}}
    case 1n+p:
      {{==}}

# s times a bit is at most s.
law mul_bit:
  for +s: Nat
  for b: Bool
  {{Nat.is_le(Nat.mul(s, U32.to_nat(Bool.to_u32(b))), s) == True{{}} : Bool}}

def mul_bit(s, b):
  match b:
    case False{{}}:
      %Equal.sym(Nat, Nat.mul(s, 0n), 0n, n.mul_zero(s)) : {{Nat.is_le(_, s) == True{{}} : Bool}}
      n.le_zero(s)
    case True{{}}:
      %Equal.sym(Nat, Nat.mul(s, 1n), s, n.mul_one(s)) : {{Nat.is_le(_, s) == True{{}} : Bool}}
      A.n.le_refl(s)

law add_le_r:
  for +t: Nat
  for +s: Nat
  for +z: Nat
  for +e: {{Nat.is_le(t, s) == True{{}} : Bool}}
  {{Nat.is_le(Nat.add(t, z), Nat.add(s, z)) == True{{}} : Bool}}

def add_le_r(t, s, z, e):
  %A.add_comm(z, t) : {{Nat.is_le(_, Nat.add(s, z)) == True{{}} : Bool}}
  %A.add_comm(z, s) : {{Nat.is_le(Nat.add(z, t), _) == True{{}} : Bool}}
  A.n.add_le(z, t, s, e)

# What k more steps of U32.log2 can add: the sum of their shifts.
def lgS(+k: Nat) -> Nat:
  match k:
    case 0n:
      0n
    case 1n+p:
      Nat.add(U32.to_nat(U32.shln(1, p)), lgS(p))

law lg:
  for +k: Nat
  for +n: U32
  for +b: Nat
  {{Nat.is_le(U32.log2.go(k, n, b), Nat.add(b, lgS(k))) == True{{}} : Bool}}

def lg(k, n, b):
  match k:
    case 0n:
      %Equal.sym(Nat, Nat.add(b, 0n), b, A.add_zero(b)) : {{Nat.is_le(b, _) == True{{}} : Bool}}
      A.n.le_refl(b)
    case 1n+p:
      +s = U32.to_nat(U32.shln(1, p))
      +t = Nat.mul(s, U32.to_nat(Bool.to_u32(U32.is_ne(U32.shrn(n, s), 0))))
      +tle = mul_bit(s, U32.is_ne(U32.shrn(n, s), 0))
      +x = add_le_r(t, s, lgS(p), tle)
      +y = A.n.add_le(b, Nat.add(t, lgS(p)), Nat.add(s, lgS(p)), x)
      +z = Equal.trans(Bool, Nat.is_le(Nat.add(Nat.add(b, t), lgS(p)), Nat.add(b, Nat.add(s, lgS(p)))),
        Nat.is_le(Nat.add(b, Nat.add(t, lgS(p))), Nat.add(b, Nat.add(s, lgS(p)))), True{{}},
        Equal.cong(Nat, Bool, w => Nat.is_le(w, Nat.add(b, Nat.add(s, lgS(p)))), Nat.add(Nat.add(b, t), lgS(p)), Nat.add(b, Nat.add(t, lgS(p))), A.add_assoc(b, t, lgS(p))), y)
      A.n.le_trans(U32.log2.go(p, U32.shrn(n, t), Nat.add(b, t)), Nat.add(Nat.add(b, t), lgS(p)), Nat.add(b, Nat.add(s, lgS(p))),
        lg(p, U32.shrn(n, t), Nat.add(b, t)), z)

law depth.go.le:
  for b: Bool
  for +n: U32
  {{Nat.is_le(B3.depth.go(b, n), 32n) == True{{}} : Bool}}

def depth.go.le(b, n):
  match b:
    case True{{}}:
      {{==}}
    case False{{}}:
      lg(5n, (n - 1 : U32), 0n)

# A span's tree is at most 32 deep (2^32 chunks).
law depth.le32:
  for +n: U32
  {{Nat.is_le(B3.depth(n), 32n) == True{{}} : Bool}}

def depth.le32(n):
  depth.go.le(U32.is_le(n, 1), n)

law cpu.go:
  for +k: Nat
  for a: Array<U32>
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +ek: {{Nat.is_le(k, 32n) == True{{}} : Bool}}
  {{B3.hash.go(~share, k, a, cb, nch, last, rf) == ref.go(k, a, cb, nch, last, rf) : B3.CV}}

def cpu.go(k, a, cb, nch, last, rf, ek):
  match k:
    case 0n:
      {{==}}
    case 1n+p:
      +ku = U32.from_nat(1n+p)
      cpu.tree(1n+p, a, clone.w(a), ku, {{==}}, ek, 0, nch, cb, nch, last, rf, A.n.le_refl({TN("nch")}),
        B3.big(1n+p, nch), {{==}}, {F("ku", "nch", "0")}, {{==}}, U32.is_eq(ku, 5), {{==}}, U32.is_eq(ku, 3), {{==}})

# The CPU's 8-lane tree is the scalar tree, for every array and every span.
law cpu.at:
  for a: Array<U32>
  for +cb: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  {{B3.hash.at(~share, a, cb, nch, last, rf) == ref.go(B3.depth(nch), a, cb, nch, last, rf) : B3.CV}}

def cpu.at(a, cb, nch, last, rf):
  cpu.go(B3.depth(nch), a, cb, nch, last, rf, depth.le32(nch))
'''


def text():
    return helpers() + cpu_tree() + top()
