# BLAKE3 for JavaScript, from Bend: `bend blake3.bend -o blake3.mjs` emits an
# ES module of these defs, which index.js drives. b3scalar.bend is
# blake3.bend's scalar half (gen_blake3.py --scalar): the JS target runs
# sequentially, so the 8-lane code would only cost.
#
# An array holds a span's bytes as little-endian words, zeros to the end of
# its last 64-byte block; a CV is {$: "CV", h0..h7}; key is a CV (IV() in
# the default mode) and kf the mode flag (0, 16, 32 or 64).
import Base
import ./b3scalar.bend as B3

def fork(a: Array<U32>) -> Array<U32> & Array<U32>:
  Array.fork(U32, a)

def IV() -> B3.CV:
  B3.IV()

# The BLAKE3 hash of `len` bytes, default mode, in one call.
def hash(a: Array<U32>, +len: U32) -> B3.CV:
  B3.hash(~fork, a, len)

# The CV of a span: nch chunks counted from cb, the last holding `last`
# bytes, rf 0 (a subtree) or 8 (ROOT, a whole input).
def span(a: Array<U32>, +cb: U32, +nch: U32, +last: U32, +rf: U32, +key: B3.CV,
  +kf: U32) -> B3.CV:
  B3.hash.at.k(~fork, a, cb, nch, last, rf, key, kf)

def parent(l: B3.CV, r: B3.CV, +key: B3.CV, +kf: U32) -> B3.CV:
  B3.parent.k(l, r, 0, key, kf)

# The roots before their last compression, and the extended output.
def chunk.root(a: Array<U32>, +cb: U32, +last: U32, +key: B3.CV, +kf: U32) -> B3.Root:
  B3.chunk.root(a, cb, last, key, kf)

def parent.root(l: B3.CV, r: B3.CV, +key: B3.CV, +kf: U32) -> B3.Root:
  B3.parent.root(l, r, key, kf)

def root.out(r: B3.Root, +t0: U32, +t1: U32) -> B3.CV & B3.CV:
  B3.root.out(r, t0, t1)
