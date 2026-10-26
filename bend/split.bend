# One input, hashed by the CPU and the GPU at once.
#
# BLAKE3's tree has a right spine (paper §2.1): from the root, every node's
# left child is a complete subtree of 2^(depth(m) - 1) of its m chunks, and
# its right child is the next node of the spine. A plan gives each of the
# first j left children, and what is left under them, to one device: bit i
# of the plan owns the left child at depth i, bit j the remainder (1 is the
# GPU, 0 the CPU). Each device hashes only its own subtrees, all of them in
# one parallel run (the GPU's in one bang), and lists their CVs in spine
# order; `merge` folds the two lists back up the spine, ROOT on the top.
#
# The devices run in two processes (bench/duo.bend): a Bend run owns its
# heap and pool, and a bang holds the run until the GPU is done, so one run
# cannot keep both busy.
#
# Like blake3.bend, every def here takes the read-sharing as `~dup`
# (hash.bend passes Array.fork), so nothing here is @unsafe.
import Base
import ./blake3.bend as B3

# Whether device `me` owns the node of the plan's low bit.
def mine(+plan: U32, +me: U32) -> Bool:
  U32.is_eq((plan .&. 1 : U32), me)

# The CV of the n chunks from chunk c (n <= 2^k) of a span of nch chunks
# from word 0 of `a`, its last holding `last` bytes, counters from 0; never
# ROOT. On the CPU's 8-lane tree.
def sub8(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +c: U32, +n: U32, +nch: U32, +last: U32,
  +lv: U32) -> B3.CV:
  match k:
    case 0n:
      B3.chunk(a, c, 0, nch, last, 0)
    case 1n+p:
      +ku = U32.from_nat(k)
      B3.tree8(~dup, k, ku, B3.kind(ku, n, c, nch, last), dup(a), c, n, 0,
        nch, last, 0)

# The same on the GPU's tree, with leaves of 4^(lv/2) chunks.
def subg(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +c: U32, +n: U32, +nch: U32, +last: U32,
  +lv: U32) -> B3.CV:
  match k:
    case 0n:
      B3.chunk(a, c, 0, nch, last, 0)
    case 1n+p:
      +ku = U32.from_nat(k)
      B3.treeg(~dup, k, ku, B3.kind1(ku, n, c, nch, last, lv), dup(a), c, n,
        0, nch, last, lv, 0)

# One node's CV if this device owns it, else nothing.
def own(~dup: Array<U32> -> Array<U32> & Array<U32>,
  ~sub: Nat -> Array<U32> -> U32 -> U32 -> U32 -> U32 -> U32 -> B3.CV,
  b: Bool, +k: Nat, a: Array<U32>, +c: U32, +n: U32, +nch: U32, +last: U32,
  +lv: U32) -> List<B3.CV>:
  match b:
    case True{}:
      [sub(k, a, c, n, nch, last, lv)]
    case False{}:
      _ = a
      []

def cat(l: List<B3.CV>, r: List<B3.CV>) -> List<B3.CV>:
  match l:
    case Nil{}:
      r
    case Con{h, t}:
      h <> cat(t, r)

# Device me's CVs along the spine over chunks c..c+m, in order: j more
# levels of left children, then the remainder. `stop` says the node is a
# single chunk (m <= 1), so it is the remainder whatever j is left. Like
# blake3.bend's trees, a node holds two read handles of the input.
def spine(~dup: Array<U32> -> Array<U32> & Array<U32>,
  ~sub: Nat -> Array<U32> -> U32 -> U32 -> U32 -> U32 -> U32 -> B3.CV,
  j: Nat, stop: Bool, aa: Array<U32> & Array<U32>, +c: U32, +m: U32,
  +plan: U32, +me: U32, +nch: U32, +last: U32, +lv: U32) -> List<B3.CV>:
  match j stop:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      own(~dup, ~sub, mine(plan, me), B3.depth(m), a1, c, m, nch, last, lv)
    case 1n+p True{}:
      (a1, a2) = aa
      _ = a2
      own(~dup, ~sub, mine(plan, me), B3.depth(m), a1, c, m, nch, last, lv)
    case 1n+p False{}:
      (a1, a2) = aa
      +q = U32.log2((m - 1 : U32))
      +h = U32.shln(1, q)
      +r = (m - h : U32)
      l t = own(~dup, ~sub, mine(plan, me), q, a1, c, h, nch, last, lv) spine(~dup, ~sub, p, U32.is_le(r, 1), dup(a2), (c + h : U32), r, (plan >> 1n : U32), me, nch, last, lv)
      cat(l, t)

# spine walked in order, for the CPU: its pool deals each task to one core
# for good, so a fork whose one side owns nothing would idle the cores dealt
# to that side. Here each owned subtree forks over the whole pool in turn.
# (The GPU's cube regrows its frontier every iteration, so spine forks.)
def spine.seq(~dup: Array<U32> -> Array<U32> & Array<U32>,
  ~sub: Nat -> Array<U32> -> U32 -> U32 -> U32 -> U32 -> U32 -> B3.CV,
  j: Nat, stop: Bool, aa: Array<U32> & Array<U32>, +c: U32, +m: U32,
  +plan: U32, +me: U32, +nch: U32, +last: U32, +lv: U32) -> List<B3.CV>:
  match j stop:
    case 0n _:
      (a1, a2) = aa
      _ = a2
      own(~dup, ~sub, mine(plan, me), B3.depth(m), a1, c, m, nch, last, lv)
    case 1n+p True{}:
      (a1, a2) = aa
      _ = a2
      own(~dup, ~sub, mine(plan, me), B3.depth(m), a1, c, m, nch, last, lv)
    case 1n+p False{}:
      (a1, a2) = aa
      +q = U32.log2((m - 1 : U32))
      +h = U32.shln(1, q)
      +r = (m - h : U32)
      l = own(~dup, ~sub, mine(plan, me), q, a1, c, h, nch, last, lv)
      cat(l, spine.seq(~dup, ~sub, p, U32.is_le(r, 1), dup(a2), (c + h : U32), r, (plan >> 1n : U32), me, nch, last, lv))

# A CV taken from one device's list, and both lists after it.
type Take is Type:
  Take{cv: B3.CV, g: List<B3.CV>, c: List<B3.CV>}

def take.g(g: List<B3.CV>, c: List<B3.CV>) -> Take:
  match g:
    case Nil{}:
      Take{B3.IV(), [], c}
    case Con{h, t}:
      Take{h, t, c}

def take.c(g: List<B3.CV>, c: List<B3.CV>) -> Take:
  match c:
    case Nil{}:
      Take{B3.IV(), g, []}
    case Con{h, t}:
      Take{h, g, t}

# The next CV of the owner's list (b: the GPU's).
def take(b: Bool, g: List<B3.CV>, c: List<B3.CV>) -> Take:
  match b:
    case True{}:
      take.g(g, c)
    case False{}:
      take.c(g, c)

# Folds both devices' CVs up the spine of m chunks, the walk spine takes:
# s holds this node's left child (or the remainder), taken from its owner's
# list, and what is left of both lists; the top parent takes rf.
def merge(j: Nat, stop: Bool, +m: U32, +plan: U32, s: Take, +rf: U32) ->
  B3.CV:
  match j stop s:
    case 0n _ Take{x, g, c}:
      _ = g
      _ = c
      x
    case 1n+p True{} Take{x, g, c}:
      _ = g
      _ = c
      x
    case 1n+p False{} Take{x, g, c}:
      +h = U32.shln(1, U32.log2((m - 1 : U32)))
      +r = (m - h : U32)
      +pl = (plan >> 1n : U32)
      B3.parent(x, merge(p, U32.is_le(r, 1), r, pl, take(mine(pl, 1), g, c), 0), rf)

# The GPU's and the CPU's share of a span of nch >= 2 chunks: spine over
# all of it from chunk 0.
def side.g(~dup: Array<U32> -> Array<U32> & Array<U32>,
  j: Nat, a: Array<U32>, +nch: U32, +last: U32, +plan: U32, +lv: U32) ->
  List<B3.CV>:
  spine(~dup, ~(k => a => c => n => x => y => z => subg(~dup, k, a, c, n, x, y, z)),
    j, U32.is_le(nch, 1), dup(a), 0, nch, plan, 1, nch, last, lv)

def side.c(~dup: Array<U32> -> Array<U32> & Array<U32>,
  j: Nat, a: Array<U32>, +nch: U32, +last: U32, +plan: U32) -> List<B3.CV>:
  spine.seq(~dup, ~(k => a => c => n => x => y => z => sub8(~dup, k, a, c, n, x, y, z)),
    j, U32.is_le(nch, 1), dup(a), 0, nch, plan, 0, nch, last, 0)

# The root CV of a span of nch >= 2 chunks from both shares.
def root(j: Nat, +nch: U32, +plan: U32, g: List<B3.CV>, c: List<B3.CV>) ->
  B3.CV:
  merge(j, U32.is_le(nch, 1), nch, plan, take(mine(plan, 1), g, c), B3.ROOT())

# Slices
# ------
# A spine share costs the GPU as much as the whole input: its smaller
# subtrees get fewer lanes, and a lane that is not one of ~16384 runs at its
# own latency, not at the memory's bandwidth (ADR 0011). Slices keep every
# lane. A whole input of 2^(k+6) chunks is 16 slices, each a whole subtree
# of 2^(k+2) chunks; lane l of 2^k hashes the 4-chunk group l of each of the
# GPU's first G slices (g4), so the GPU's share is G/16 of the input, still
# on all 2^k lanes and one balanced tree. A join zips its halves' lists of G
# CVs group for group (blake3.bend's GQuad does the same with four), so
# after k levels the list holds slices 0..G-1. The CPU hashes slices G..15
# with tree8, one after another, and slice.root folds the 16.

# The lane's last g CVs, newest first in acc.
def lane.go(n: Nat, r: Array<U32> & B3.CV, +c: U32, +t: U32, +st: U32,
  acc: List<B3.CV>) -> List<B3.CV>:
  match n:
    case 0n:
      (a, x) = r
      _ = a
      x <> acc
    case 1n+p:
      (a, x) = r
      +c2 = (c + st : U32)
      +t2 = (t + st : U32)
      lane.go(p, B3.g4(a, c2, t2, 0), c2, t2, st, x <> acc)

# One lane: g 4-chunk groups from array chunk c (counter t), st chunks
# apart, as a list from the last group to the first.
def lane(n: Nat, a: Array<U32>, +c: U32, +t: U32, +st: U32) -> List<B3.CV>:
  match n:
    case 0n:
      _ = a
      []
    case 1n+p:
      lane.go(p, B3.g4(a, c, t, 0), c, t, st, [])

# Parents of two lists, element by element, in reverse order.
def zip.go(x: List<B3.CV>, y: List<B3.CV>, acc: List<B3.CV>) -> List<B3.CV> :
  match x y:
    case Con{a, xs} Con{b, ys}:
      zip.go(xs, ys, B3.parent(a, b, 0) <> acc)
    case _ _:
      acc

def rev.go(xs: List<B3.CV>, acc: List<B3.CV>) -> List<B3.CV>:
  match xs:
    case Nil{}:
      acc
    case Con{h, t}:
      rev.go(t, h <> acc)

# The lanes' lists, slice 0 first: they start last-first and every level of
# zips reverses them.
def orient(b: Bool, xs: List<B3.CV>) -> List<B3.CV>:
  match b:
    case True{}:
      rev.go(xs, [])
    case False{}:
      xs

# 2^k lanes from the one whose first group is at array chunk c (counter t).
def qtreel(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, aa: Array<U32> & Array<U32>, +c: U32, +t: U32, +st: U32,
  +g: Nat) -> List<B3.CV>:
  match k:
    case 0n:
      (a1, a2) = aa
      _ = a2
      lane(g, a1, c, t, st)
    case 1n+p:
      (a1, a2) = aa
      +h = U32.shln(4, p)
      l r = qtreel(~dup, p, dup(a1), c, t, st, g) qtreel(~dup, p, dup(a2), (c + h : U32), (t + h : U32), st, g)
      zip.go(l, r, [])

# The GPU's share of a whole input of 2^(k+6) chunks: the CVs of slices
# 0..g-1 (call with !).
def slice.g(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +g: Nat) -> List<B3.CV>:
  orient(U32.is_eq((U32.from_nat(k) .&. 1 : U32), 0),
    qtreel(~dup, k, dup(a), 0, 0, U32.shln(4, k), g))

def slice.c.go(~dup: Array<U32> -> Array<U32> & Array<U32>,
  n: Nat, aa: Array<U32> & Array<U32>, +s: U32, +k2: Nat, +sz: U32,
  +nch: U32) -> List<B3.CV>:
  match n:
    case 0n:
      (a1, a2) = aa
      _ = a1
      _ = a2
      []
    case 1n+p:
      (a1, a2) = aa
      x = sub8(~dup, k2, a1, (s * sz : U32), sz, nch, 1024, 0)
      x <> slice.c.go(~dup, p, dup(a2), (s + 1 : U32), k2, sz, nch)

# The CPU's share: the CVs of slices g..15, each on the whole pool in turn.
def slice.c(~dup: Array<U32> -> Array<U32> & Array<U32>,
  +k: Nat, a: Array<U32>, +g: U32) -> List<B3.CV>:
  +sz = U32.shln(4, k)
  slice.c.go(~dup, U32.to_nat((16 - g : U32)), dup(a), g, 2n+k, sz,
    (sz << 4n : U32))

def pairs(xs: List<B3.CV>) -> List<B3.CV>:
  match xs:
    case Con{a, Con{b, rest}}:
      B3.parent(a, b, 0) <> pairs(rest)
    case _:
      []

def top(xs: List<B3.CV>) -> B3.CV:
  match xs:
    case Con{a, Con{b, _}}:
      B3.parent(a, b, B3.ROOT())
    case _:
      B3.IV()

# The root CV from the GPU's slices g and the CPU's c, 16 in all.
def slice.root(g: List<B3.CV>, c: List<B3.CV>) -> B3.CV:
  top(pairs(pairs(pairs(cat(g, c)))))
