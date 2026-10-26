# The library's engine
# ====================
#
# libblake3-bend is the official BLAKE3 C library with one change: a big
# power-of-two subtree, the part of an update that hashes in parallel, is
# handed to this program instead of the C SIMD loop (see blake3_bend.c).
# It runs on a thread of its own inside the host process, forever: each
# Eng.next waits for a caller's job, Bend hashes it all at once (every
# span's tree in parallel), and Eng.done hands the CVs back. The CV stack,
# keys, flags, finalization and extended output stay in C. A job can also
# be a list of files (turboblake's fast path), hashed as bend/b3sum.bend does.

import Base
import ../blake3.bend as B3
import ../hash.bend as H
import ../b3io.bend as F

# Subtrees to hash: each a span (see blake3.bend's hash.at) of nch chunks,
# the last of them `last` bytes; the chunk counter of its first is hi:cb.
# key and kf are the mode (blake3.bend's .k defs): IV and 0 in the default
# mode.
type Spans is Type:
  SpNil{}
  SpOne{arr: Array<U32>, cb: U32, hi: U32, nch: U32, last: U32, key: B3.CV,
    kf: U32}
  SpTwo{l: Spans, r: Spans}

# Their chaining values, in the same shape.
type CVs is Data:
  CvNil{}
  CvOne{cv: B3.CV}
  CvTwo{l: CVs, r: CVs}

# A job: spans of memory, or files (a caller's paths, loaded by
# B3IO.take as b3sum loads its arguments: in parallel, mapped, streamed).
type Job is Type:
  JSpans{s: Spans}
  JFiles{}

# Waits for the next job (effects in engine.c).
def Eng.next() -> IO(Job):
  import "./engine.c"
  import "./engine.js"

# Answers the CVs to the caller that sent the spans.
def Eng.done(c: CVs) -> IO(Unit):
  import "./engine.c"
  import "./engine.js"

# A span's CV: the default mode's tree, or the keyed one.
def span(dflt: Bool, a: Array<U32>, +cb: U32, +hi: U32, +nch: U32, +last: U32,
  +key: B3.CV, +kf: U32) -> B3.CV:
  match dflt:
    case True{}:
      H.hash.at(a, cb, hi, nch, last, 0)
    case False{}:
      H.hash8.at.k(a, cb, hi, nch, last, 0, key, kf)

# Every span at once; no span is a root (the root is always C's).
def cvs(s: Spans) -> CVs:
  match s:
    case SpNil{}:
      CvNil{}
    case SpOne{a, +cb, +hi, +nch, +last, +key, +kf}:
      CvOne{span(U32.is_eq(kf, 0), a, cb, hi, nch, last, key, kf)}
    case SpTwo{l, r}:
      x y = cvs(l) cvs(r)
      CvTwo{x, y}

# Every file at once (b3io.bend's hash), the streamed ones after; the
# hashes and errors go back in order, and the mapped files are let go.
def files(+threads: U32) -> IO(Unit):
  do IO<Unit>:
    fs : F.Files <- F.B3IO.take(threads)
    out : F.Out <- F.fill(F.hash(fs))
    n : U32 <- F.B3IO.give(out)
    F.B3IO.release()

def work(j: Job, +threads: U32) -> IO(Unit):
  match j:
    case JSpans{s}:
      Eng.done(cvs(s))
    case JFiles{}:
      files(threads)

def serve(n: Nat, +threads: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        j : Job <- Eng.next()
        work(j, threads)
        serve(p, threads)

# 2^32 jobs a lap, and laps without end: the host's exit stops it.
def laps(n: Nat, +threads: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        serve(U32.to_nat(4294967295), threads)
        laps(p, threads)

def main() -> IO(Unit):
  do IO<Unit>:
    n : U32 <- IO.thread_count()
    laps(U32.to_nat(4294967295), n)
