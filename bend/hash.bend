# The BLAKE3 entry points that run: blake3.bend's trees with Array.fork as
# their `~dup`, so both halves of every tree node read the one input at once
# with no copy. Array.fork is @unsafe in Base (it hands out two handles of
# one array), which is why it lives here and not in blake3.bend: the laws
# (LAWS.bend) import only blake3.bend, whose defs are all proof-safe.
import Base
import ./blake3.bend as B3
import ./split.bend as S

def fork(a: Array<U32>) -> Array<U32> & Array<U32>:
  Array.fork(U32, a)

# The CV of a span (see blake3.bend's hash.at), on the CPU's 8-lane tree.
def hash.at(a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> B3.CV:
  B3.hash.at(~fork, a, cb, nch, last, rf)

# The BLAKE3 hash (first 32 bytes) of `len` bytes held in `a`, for the CPU.
def hash(a: Array<U32>, +len: U32) -> B3.CV:
  B3.hash(~fork, a, len)

# A span on the GPU-shaped tree (call with !).
def hash1.at(a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) -> B3.CV:
  B3.hash1.at(~fork, a, cb, nch, last, rf)

# The hash on the GPU-shaped tree: `H.hash1!(a, len)` runs it on the GPU.
def hash1(a: Array<U32>, +len: U32) -> B3.CV:
  B3.hash1(~fork, a, len)

# A span with its bao outboard pairs (see blake3.bend's tree8o).
def hash.ob.at(a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32) ->
  B3.CV & B3.OB:
  B3.hash.ob.at(~fork, a, cb, nch, last, rf)

# The hash of `len` bytes held in `a`, with its outboard pairs.
def hash.ob(a: Array<U32>, +len: U32) -> B3.CV & B3.OB:
  B3.hash.ob(~fork, a, len)

# One device's share of a span split between the CPU and the GPU (see
# split.bend): the GPU's (call with !) and the CPU's CVs along the spine.
def side.g(j: Nat, a: Array<U32>, +nch: U32, +last: U32, +plan: U32,
  +lv: U32) -> List<B3.CV>:
  S.side.g(~fork, j, a, nch, last, plan, lv)

def side.c(j: Nat, a: Array<U32>, +nch: U32, +last: U32, +plan: U32) ->
  List<B3.CV>:
  S.side.c(~fork, j, a, nch, last, plan)
