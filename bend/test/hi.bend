# Spans past 4 TiB: chunk counters of 2^32 and up, whose high word (hi) the
# trees take beside the low one (cb). Prints "<case> <tree> <cv>" for every
# case below through every tree that takes a span: the CPU's 8-lane tree,
# the GPU's tree (run here on the CPU pool, no bang), the outboard tree, the
# keyed 8-lane tree and the scalar tree, one line a case. test/hi.py compares them with the
# official crate's subtree CVs (hazmat, at the same input offset).
import Base
import ../blake3.bend as B3
import ../hash.bend as H

def byte(+i: U32, +len: U32) -> U32:
  ((i % 251 : U32) .&. (0 - Bool.to_u32(U32.is_lt(i, len)) : U32) : U32)

def word(+j: U32, +len: U32) -> U32:
  +i = (j << 2n : U32)
  (byte(i, len) .|. (byte((i + 1 : U32), len) << 8n : U32) .|.
    (byte((i + 2 : U32), len) << 16n : U32) .|.
    (byte((i + 3 : U32), len) << 24n : U32) : U32)

def fill(n: Nat, a: Array<U32>, +j: U32, +len: U32) -> Array<U32>:
  match n:
    case 0n:
      a
    case 1n+p:
      a[j] <- word(j, len)
      fill(p, a, (j + 1 : U32), len)

# len bytes, byte i = i % 251, zero to the end of the last block. Indexes
# wrap, so the array has a slot for every word.
def input(+len: U32) -> Array<U32>:
  +w = U32.max((((len + 63 : U32) >> 6n : U32) << 4n : U32), 16)
  +d = B3.depth(w)
  fill(U32.to_nat(w), [0 : U32^d], 0, len)

def fork(a: Array<U32>) -> Array<U32> & Array<U32>:
  Array.fork(U32, a)

# The key bytes 0, 1, ..., 31 as words.
def key() -> B3.CV:
  B3.CV{50462976, 117835012, 185207048, 252579084, 319951120, 387323156,
    454695192, 522067228}

def tree(name: String, cv: B3.CV) -> String:
  " " ++ name ++ " " ++ B3.hex(cv)

# The trees, each on its own handle of the input (forked: no copies).
def t.ob(r: Array<U32> & Array<U32>, +cb: U32, +hi: U32, +n: U32, +last: U32) -> String:
  (a, b) = r
  tree("ob", Pair.fst(B3.CV, B3.OB, H.hash.ob.at(a, cb, hi, n, last, 0))) ++
    tree("tree1", B3.hash.at.k(~fork, b, cb, hi, n, last, 0, B3.IV(), 0))

def t.keyed(r: Array<U32> & Array<U32>, +cb: U32, +hi: U32, +n: U32, +last: U32) -> String:
  (a, b) = r
  tree("keyed", H.hash8.at.k(a, cb, hi, n, last, 0, key(), 16)) ++
    t.ob(fork(b), cb, hi, n, last)

def t.gpu(r: Array<U32> & Array<U32>, +cb: U32, +hi: U32, +n: U32, +last: U32) -> String:
  (a, b) = r
  tree("gpu", H.hash1.at(a, cb, hi, n, last, 0)) ++ t.keyed(fork(b), cb, hi, n, last)

def t.cpu(r: Array<U32> & Array<U32>, +cb: U32, +hi: U32, +n: U32, +last: U32) -> String:
  (a, b) = r
  tree("cpu", H.hash.at(a, cb, hi, n, last, 0)) ++ t.gpu(fork(b), cb, hi, n, last)

# One span, one line: the len-byte input as nch chunks with counters from
# hi:cb, through every tree.
def one(name: String, +len: U32, +cb: U32, +hi: U32) -> String:
  +n = B3.chunks(len)
  name ++ t.cpu(fork(input(len)), cb, hi, n, B3.tail(len, n))

# The cases, as test/hi.py reads them: name, bytes, chunk counter (hi:cb).
def main() -> IO(Unit):
  do IO<Unit>:
    IO.print(one("chunk", 1024, 0, 1))
    IO.print(one("edge", 3077, 4294967280, 179951))
    IO.print(one("leaf32", 32768, 2147483648, 1))
    IO.print(one("seg", 1073741824, 0, 1))
    IO.print(one("lastseg", 1073729479, 7340032, 3))
