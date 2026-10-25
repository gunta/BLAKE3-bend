# The library's engine
# ====================
#
# libblake3-bend is the official BLAKE3 C library with one change: a big
# power-of-two subtree, the part of an update that hashes in parallel, is
# handed to this program instead of the C SIMD loop (see blake3_bend.c).
# It runs on a thread of its own inside the host process, forever: each
# Eng.next waits for a caller's spans, Bend hashes them all at once (every
# span's tree in parallel), and Eng.done hands their CVs back. The CV
# stack, keys, flags, finalization and extended output stay in C.

import Base
import ../blake3.bend as B3
import ../hash.bend as H

# Subtrees to hash: each a span (see blake3.bend's hash.at) of nch chunks,
# the last of them `last` bytes; the chunk counter of its first is cb.
type Spans is Type:
  SpNil{}
  SpOne{arr: Array<U32>, cb: U32, nch: U32, last: U32}
  SpTwo{l: Spans, r: Spans}

# Their chaining values, in the same shape.
type CVs is Data:
  CvNil{}
  CvOne{cv: B3.CV}
  CvTwo{l: CVs, r: CVs}

# Waits for the next spans (effects in engine.c).
def Eng.next() -> IO(Spans):
  import "./engine.c"
  import "./engine.js"

# Answers the CVs to the caller that sent the spans.
def Eng.done(c: CVs) -> IO(Unit):
  import "./engine.c"
  import "./engine.js"

# Every span at once; no span is a root (the root is always C's).
def cvs(s: Spans) -> CVs:
  match s:
    case SpNil{}:
      CvNil{}
    case SpOne{a, cb, nch, last}:
      CvOne{H.hash.at(a, cb, nch, last, 0)}
    case SpTwo{l, r}:
      x y = cvs(l) cvs(r)
      CvTwo{x, y}

def serve(n: Nat) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        s : Spans <- Eng.next()
        Eng.done(cvs(s))
        serve(p)

# 2^32 jobs a lap, and laps without end: the host's exit stops it.
def laps(n: Nat) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        serve(U32.to_nat(4294967295))
        laps(p)

def main() -> IO(Unit):
  laps(U32.to_nat(4294967295))
