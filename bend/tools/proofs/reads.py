"""Reads: a read hands its array back (get.eta), so do the scalar and 8-lane
loaders (ld.eta, ld8.words), and lane l of the 8-lane block is the scalar
block of chunk l (b128.lane). Arrays are linear in proofs as in code, so a
proof that reads one array often first splits it into copies (dup.w, wits)
and moves facts about a copy back with tr."""
from .common import L

HEAD = '''
# Copies
# ------
#
# Arrays are linear in proofs as in code, so a proof that reads a twice
# first splits it into two copies, each equal to a (dup.w, Array.clone in
# proof form), and tr moves a fact about a copy back to a.

def Two(-a: Array<U32>) -> Type:
  Exists(Array<U32>, x => Exists(Array<U32>, y => {x == a : Array<U32>} & {y == a : Array<U32>}))

law anode.cong:
  for -x1: Array<U32>
  for -xs: Array<U32>
  for -y1: Array<U32>
  for -ys: Array<U32>
  for e1: {x1 == xs : Array<U32>}
  for e2: {y1 == ys : Array<U32>}
  {ANode{x1, y1} == ANode{xs, ys} : Array<U32>}

def anode.cong(x1, xs, y1, ys, e1, e2):
  %Equal.sym(Array<U32>, x1, xs, e1) : {ANode{_, y1} == ANode{xs, ys} : Array<U32>}
  %Equal.sym(Array<U32>, y1, ys, e2) : {ANode{xs, _} == ANode{xs, ys} : Array<U32>}
  {==}

def dup.w.node(-xs: Array<U32>, -ys: Array<U32>, rx: Two(xs), ry: Two(ys)) -> Two(ANode{xs, ys}):
  match rx:
    case (x1, rx2):
      match rx2:
        case (x2, xe):
          match xe:
            case (ex1, ex2):
              match ry:
                case (y1, ry2):
                  match ry2:
                    case (y2, ye):
                      match ye:
                        case (ey1, ey2):
                          (ANode{x1, y1}, (ANode{x2, y2}, (anode.cong(x1, xs, y1, ys, ex1, ey1), anode.cong(x2, xs, y2, ys, ex2, ey2))))

law dup.w:
  for a: Array<U32>
  Two(a)

def dup.w(a):
  match a:
    case ALeaf{+x}:
      (ALeaf{x}, (ALeaf{x}, ({==}, {==})))
    case ANode{xs, ys}:
      dup.w.node(xs, ys, dup.w(xs), dup.w(ys))

# A fact about a copy is a fact about a.
law tr:
  for -q: Array<U32> -> Type
  for -x: Array<U32>
  for -a: Array<U32>
  for e: {x == a : Array<U32>}
  for p: q(x)
  q(a)

def tr(q, x, a, e, p):
  %e : q(_)
  p

law eq.trans:
  for -x: Array<U32>
  for -b: Array<U32>
  for -a: Array<U32>
  for e1: {x == b : Array<U32>}
  for e2: {b == a : Array<U32>}
  {x == a : Array<U32>}

def eq.trans(x, b, a, e1, e2):
  Equal.trans(Array<U32>, x, b, a, e1, e2)

# The laws' copy is Array.fork's own body: (a, a).
law clone.dup:
  for a: Array<U32>
  {Array.clone(U32, a) == (a, a) : Array<U32> & Array<U32>}

def clone.dup(a):
  match a:
    case ALeaf{x}:
      {==}
    case ANode{xs, ys}:
      %Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, xs), (xs, xs), clone.dup(xs)) : {Array.clone.node(U32, _, Array.clone(U32, ys)) == (ANode{xs, ys}, ANode{xs, ys}) : Array<U32> & Array<U32>}
      %Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, ys), (ys, ys), clone.dup(ys)) : {Array.clone.node(U32, (xs, xs), _) == (ANode{xs, ys}, ANode{xs, ys}) : Array<U32> & Array<U32>}
      {==}

# Reads
# -----

law size.eta:
  for a: Array<U32>
  {Array.size(U32, a) == (a, Pair.snd(Array<U32>, U32, Array.size(U32, a))) : Array<U32> & U32}

def size.eta(a):
  match a:
    case ALeaf{x}:
      {==}
    case ANode{xs, ys}:
      %Equal.sym(Array<U32> & U32, Array.size(U32, xs), (xs, Pair.snd(Array<U32>, U32, Array.size(U32, xs))), size.eta(xs)) :
        {Array.size.node(U32, ys, _) == (ANode{xs, ys}, Pair.snd(Array<U32>, U32, Array.size.node(U32, ys, _))) : Array<U32> & U32}
      {==}

law get.go.eta:
  for a: Array<U32>
  for n: U32
  for +i: U32
  for z: Bool
  {Array.get.go(U32, a, n, i, z) == (a, Pair.snd(Array<U32>, U32, Array.get.go(U32, a, n, i, z))) : Array<U32> & U32}

def get.go.eta(a, n, i, z):
  match a z:
    case ALeaf{x} _:
      {==}
    case ANode{xs, ys} True{}:
      +h = U32.shr(n)
      %Equal.sym(Array<U32> & U32, Array.get.go(U32, xs, h, i, U32.is_lt(i, U32.shr(h))), (xs, Pair.snd(Array<U32>, U32, Array.get.go(U32, xs, h, i, U32.is_lt(i, U32.shr(h))))), get.go.eta(xs, h, i, U32.is_lt(i, U32.shr(h)))) :
        {Array.swap.lo(U32, ys, _) == (ANode{xs, ys}, Pair.snd(Array<U32>, U32, Array.swap.lo(U32, ys, _))) : Array<U32> & U32}
      {==}
    case ANode{xs, ys} False{}:
      +h = U32.shr(n)
      +j = U32.sub(i, h)
      %Equal.sym(Array<U32> & U32, Array.get.go(U32, ys, h, j, U32.is_lt(j, U32.shr(h))), (ys, Pair.snd(Array<U32>, U32, Array.get.go(U32, ys, h, j, U32.is_lt(j, U32.shr(h))))), get.go.eta(ys, h, j, U32.is_lt(j, U32.shr(h)))) :
        {Array.swap.hi(U32, xs, _) == (ANode{xs, ys}, Pair.snd(Array<U32>, U32, Array.swap.hi(U32, xs, _))) : Array<U32> & U32}
      {==}

# Word i of a.
def rd(a: Array<U32>, +i: U32) -> U32:
  Pair.snd(Array<U32>, U32, Array.get(U32, a, i))

law get.at.eta:
  for r: Array<U32> & U32
  for +i: U32
  {Array.get.at(U32, i, r) == (Pair.fst(Array<U32>, U32, r), Pair.snd(Array<U32>, U32, Array.get.at(U32, i, r))) : Array<U32> & U32}

def get.at.eta(r, i):
  match r:
    case (a, +n):
      +j = U32.and(i, U32.sub(n, 1))
      get.go.eta(a, n, j, U32.is_lt(j, U32.shr(n)))

law size.fst:
  for a: Array<U32>
  {Pair.fst(Array<U32>, U32, Array.size(U32, a)) == a : Array<U32>}

def size.fst(a):
  Equal.cong(Array<U32> & U32, Array<U32>, p => Pair.fst(Array<U32>, U32, p), Array.size(U32, a), (a, Pair.snd(Array<U32>, U32, Array.size(U32, a))), size.eta(a))

def get.eta.h(-a: Array<U32>, +i: U32, r: Two(a)) -> {Array.get(U32, a, i) == (a, rd(a, i)) : Array<U32> & U32}:
  match r:
    case (x, r2):
      match r2:
        case (y, e):
          match e:
            case (ex, ey):
              %tr(c => {Pair.fst(Array<U32>, U32, Array.size(U32, c)) == c : Array<U32>}, y, a, ey, size.fst(y)) :
                {Array.get.at(U32, i, Array.size(U32, a)) == (_, Pair.snd(Array<U32>, U32, Array.get.at(U32, i, Array.size(U32, a)))) : Array<U32> & U32}
              tr(c => {Array.get.at(U32, i, Array.size(U32, c)) == (Pair.fst(Array<U32>, U32, Array.size(U32, c)), Pair.snd(Array<U32>, U32, Array.get.at(U32, i, Array.size(U32, c)))) : Array<U32> & U32},
                x, a, ex, get.at.eta(Array.size(U32, x), i))

# A read hands its array back.
law get.eta:
  for a: Array<U32>
  for +i: U32
  {Array.get(U32, a, i) == (a, rd(a, i)) : Array<U32> & U32}

def get.eta(a, i):
  get.eta.h(a, i, dup.w(a))
'''


def ld_eta():
    """ld's sixteen reads, one copy of a each: ld.st<k> from read k on."""
    ix = lambda k: "w" if k == 0 else f"(w + {k} : U32)"
    out = []
    for k in range(15, -1, -1):
        ms = [f"m{j}" for j in range(k)]
        args = (["w"] if k < 15 else []) + ms
        stmt = f"B3.ld.s{k}(Array.get(U32, a, {ix(k)})" + "".join(", " + x for x in args) + ")"
        goal = f"{{{stmt} == (a, Pair.snd(Array<U32>, B3.M16, {stmt})) : Array<U32> & B3.M16}}"
        inner = f"B3.ld.s{k}(_" + "".join(", " + x for x in args) + ")"
        motive = f"{{{inner} == (a, Pair.snd(Array<U32>, B3.M16, {inner})) : Array<U32> & B3.M16}}"
        fact = (f"tr(c => {{Array.get(U32, c, {ix(k)}) == (c, rd(c, {ix(k)})) : Array<U32> & U32}}, "
                f"x, a, eq.trans(x, b, a, ex, eb), get.eta(x, {ix(k)}))")
        msig = "".join(f", -m{j}: U32" for j in range(k))
        margs = "".join(f", m{j}" for j in range(k))
        if k == 15:
            pre, tail = "              _ = y\n", "              {==}\n"
        else:
            pre, tail = "", f"              ld.st{k + 1}(a, y, eq.trans(y, b, a, ey, eb), w{margs}, rd(a, {ix(k)}))\n"
        out.append(f'''
def ld.st{k}.h(-a: Array<U32>, -b: Array<U32>, r: Two(b), +eb: {{b == a : Array<U32>}}, +w: U32{msig}) -> {goal}:
  match r:
    case (x, r2):
      match r2:
        case (y, e):
          match e:
            case (ex, ey):
{pre}              %Equal.sym(Array<U32> & U32, Array.get(U32, a, {ix(k)}), (a, rd(a, {ix(k)})), {fact}) :
                {motive}
{tail}
law ld.st{k}:
  for -a: Array<U32>
  for b: Array<U32>
  for +eb: {{b == a : Array<U32>}}
  for +w: U32
''' + "".join(f"  for -m{j}: U32\n" for j in range(k)) + f'''  {goal}

def ld.st{k}(a, b, eb, w{margs}):
  ld.st{k}.h(a, b, dup.w(b), eb, w{margs})
''')
    out.append('''
# The scalar loader hands its array back.
law ld.eta:
  for a: Array<U32>
  for +w: U32
  {B3.ld(a, w) == (a, Pair.snd(Array<U32>, B3.M16, B3.ld(a, w))) : Array<U32> & B3.M16}

def ld.eta(a, w):
  ld.st0(a, a, {==}, w)
''')
    return "".join(out)


def ld8_words():
    """ld8 is eight scalar blocks: ld8.st<k> from lane k's load on."""
    ix8 = lambda l: "w" if l == 0 else f"(w + {256 * l} : U32)"
    X = lambda l: f"Pair.snd(Array<U32>, B3.M16, B3.ld(a, {ix8(l)}))"
    out = []
    for k in range(L - 1, -1, -1):
        ms = [f"m{j}" for j in range(k)]
        args = (["w"] if k < L - 1 else []) + ms
        stmt = f"B3.ld8.s{k}(B3.ld(a, {ix8(k)})" + "".join(", " + x for x in args) + ")"
        rhs = "(a, B3.b128.of(" + ", ".join(ms + [X(j) for j in range(k, L)]) + "))"
        goal = f"{{{stmt} == {rhs} : Array<U32> & B3.B128}}"
        mot = f"{{B3.ld8.s{k}(_" + "".join(", " + x for x in args) + f") == {rhs} : Array<U32> & B3.B128}}"
        msig = "".join(f", -m{j}: B3.M16" for j in range(k))
        margs = "".join(f", m{j}" for j in range(k))
        fact = (f"tr(c => {{B3.ld(c, {ix8(k)}) == (c, Pair.snd(Array<U32>, B3.M16, B3.ld(c, {ix8(k)}))) : Array<U32> & B3.M16}}, "
                f"x, a, eq.trans(x, b, a, ex, eb), ld.eta(x, {ix8(k)}))")
        if k == L - 1:
            pre, tail = "              _ = y\n", "              {==}\n"
        else:
            pre, tail = "", f"              ld8.st{k + 1}(a, y, eq.trans(y, b, a, ey, eb), w{margs}, {X(k)})\n"
        out.append(f'''
def ld8.st{k}.h(-a: Array<U32>, -b: Array<U32>, r: Two(b), +eb: {{b == a : Array<U32>}}, +w: U32{msig}) -> {goal}:
  match r:
    case (x, r2):
      match r2:
        case (y, e):
          match e:
            case (ex, ey):
{pre}              %Equal.sym(Array<U32> & B3.M16, B3.ld(a, {ix8(k)}), (a, {X(k)}), {fact}) :
                {mot}
{tail}
law ld8.st{k}:
  for -a: Array<U32>
  for b: Array<U32>
  for +eb: {{b == a : Array<U32>}}
  for +w: U32
''' + "".join(f"  for -m{j}: B3.M16\n" for j in range(k)) + f'''  {goal}

def ld8.st{k}(a, b, eb, w{margs}):
  ld8.st{k}.h(a, b, dup.w(b), eb, w{margs})
''')
    allX = ", ".join(X(j) for j in range(L))
    out.append(f'''
# The 8-lane loader is eight scalar blocks, 256 words apart.
law ld8.words:
  for a: Array<U32>
  for +w: U32
  {{B3.ld8(a, w) == (a, B3.b128.of({allX})) : Array<U32> & B3.B128}}

def ld8.words(a, w):
  ld8.st0(a, a, {{==}}, w)
''')
    return "".join(out)


def b128_lane():
    xs = ", ".join(f"x{l}" for l in range(L))
    pick = ("def m.pick(l: Lane, " + ", ".join(f"x{l}: B3.M16" for l in range(L)) + ") -> B3.M16:\n  match l:\n" +
            "".join(f"    case L{l}{{}}:\n" + "".join(f"      _ = x{j}\n" for j in range(L) if j != l) + f"      x{l}\n"
                    for l in range(L)))
    pats = " ".join("B3.M16{" + ", ".join(f"x{l}_{i}" for i in range(16)) + "}" for l in range(L))
    cases = "".join(f"    case L{l}{{}} {pats}:\n      {{==}}\n" for l in range(L))
    return (f"\n# Lane l of eight blocks is block l.\n{pick}\nlaw b128.lane:\n  for l: Lane\n" +
            "".join(f"  for x{l}: B3.M16\n" for l in range(L)) +
            f"  {{m.at(l, B3.b128.of({xs})) == m.pick(l, {xs}) : B3.M16}}\n\n"
            f"def b128.lane(l, {xs}):\n  match l {xs.replace(',', '')}:\n{cases}")


WITS = '''
# Many copies
# -----------

def Wits(-a: Array<U32>, n: Nat) -> Type:
  match n:
    case 0n:
      Unit
    case 1n+p:
      Exists(Array<U32>, x => {x == a : Array<U32>} & Wits(a, p))

def wits.grow2(-a: Array<U32>, +p: Nat, -x: Array<U32>, +ex: {x == a : Array<U32>}, r: Two(x), rest: Wits(a, p)) -> Wits(a, 2n+p):
  match r:
    case (y, r2):
      match r2:
        case (z, e):
          match e:
            case (ey, ez):
              (y, (eq.trans(y, x, a, ey, ex), (z, (eq.trans(z, x, a, ez, ex), rest))))

def wits.grow(-a: Array<U32>, +p: Nat, w: Wits(a, 1n+p)) -> Wits(a, 2n+p):
  match w:
    case (x, w2):
      match w2:
        case (ex, rest):
          wits.grow2(a, p, x, ex, dup.w(x), rest)

law wits:
  for +n: Nat
  for a: Array<U32>
  Wits(a, 1n+n)

def wits(n, a):
  match n:
    case 0n:
      (a, ({==}, Unit{}))
    case 1n+p:
      wits.grow(a, p, wits(p, a))
'''


def text():
    return HEAD + ld_eta() + ld8_words() + b128_lane() + WITS
