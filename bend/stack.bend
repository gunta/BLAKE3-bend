# The merge stack of a streamed file
# ==================================
#
# A file mostly not in the page cache streams (b3io.bend's FStream): its
# 1 GiB segments are hashed one after another (each on every core) while
# the SSD reads the next, and their CVs merge as BLAKE3's Hasher merges
# chunks: lazily, a stack of complete subtrees, so the last merge knows it
# is the root.
#
# The merging lives here, apart from the reads: this module imports no
# effect and no Array.fork, so LAWS.bend can name it. stk.go takes the
# reads as a template: b3io runs it with its segment reads, the laws with
# pure answers, and law `stream.hash` is about this loop.

import Base
import ./blake3.bend as B3

type Stk is Data:
  KNil{}
  KCon{cv: B3.CV, rest: Stk}

def stk.pop2(s: Stk) -> Stk:
  match s:
    case KCon{r, KCon{l, rest}}:
      KCon{B3.parent(l, r, 0), rest}
    case KCon{r, KNil{}}:
      KCon{r, KNil{}}
    case KNil{}:
      KNil{}

def stk.even(+n: U32) -> Bool:
  U32.is_eq((n .&. 1 : U32), 0) && U32.is_ne(n, 0)

# Before segment n joins: merge while n (the segments so far) is even.
def stk.lazy(fuel: Nat, s: Stk, +n: U32, b: Bool) -> Stk:
  match fuel b:
    case 0n _:
      s
    case 1n+f True{}:
      +m = (n >> 1n : U32)
      stk.lazy(f, stk.pop2(s), m, stk.even(m))
    case 1n+f False{}:
      s

def stk.fin(s: Stk, r: B3.CV) -> B3.CV:
  match s:
    case KNil{}:
      r
    case KCon{l, KNil{}}:
      B3.parent(l, r, B3.ROOT())
    case KCon{l, rest}:
      stk.fin(rest, B3.parent(l, r, 0))

def stk.root(s: Stk) -> B3.CV:
  match s:
    case KCon{top, rest}:
      stk.fin(rest, top)
    case KNil{}:
      B3.IV()

# n segments to go, from segment k: rd(id, k) reads segment k of stream id
# and answers its CV.
def stk.go(~I: Data, ~rd: I -> U32 -> IO(B3.CV), n: Nat, +id: I, +k: U32, s: Stk) -> IO(B3.CV):
  match n:
    case 0n:
      IO.pure(B3.CV, stk.root(s))
    case 1n+p:
      IO.bind(B3.CV, B3.CV, rd(id, k),
        cv => stk.go(~I, ~rd, p, id, (k + 1 : U32), KCon{cv, stk.lazy(32n, s, k, stk.even(k))}))
