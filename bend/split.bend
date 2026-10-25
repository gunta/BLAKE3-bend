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
