# b3sum in Bend2
# ==============
#
# usage: b3sum [FILE]...   (any size up to 4 TiB; none, or "-", is stdin)
# Prints "<hash>  <name>" per file, like the official b3sum. B3IO.load reads
# every file in parallel into its own Array<U32>; the fork over the Files
# tree hashes the files in parallel, and each file's BLAKE3 tree is itself
# parallel, so one big file and ten thousand small ones both use every core.

import Base
import ./blake3.bend as B3
import ./b3io.bend as F

# A big file's parts hash in parallel, each a complete subtree but the
# last, and merge as BLAKE3's parents; only the top one is the root.
def segs(s: F.Segs, +rf: U32) -> B3.CV:
  match s:
    case F.SLeaf{a, cb, nch, last}:
      B3.hash.at(a, cb, nch, last, rf)
    case F.SNode{l, r}:
      x y = segs(l, 0) segs(r, 0)
      B3.parent(x, y, rf)

def hash(t: F.Files) -> F.Out:
  match t:
    case F.FNone{}:
      F.ONone{}
    case F.FFile{a, len, name}:
      F.OHash{B3.hash(a, len), name}
    case F.FSegs{s, name}:
      F.OHash{segs(s, B3.ROOT()), name}
    case F.FErr{msg, name}:
      F.OErr{msg, name}
    case F.FPair{l, r}:
      x y = hash(l) hash(r)
      F.OPair{x, y}

def files(xs: List<String>) -> List<String>:
  match xs:
    case Nil{}:
      ["-"]
    case Con{x, rest}:
      Con{x, rest}

# The arguments after the program: no file names means stdin.
def rest(xs: List<String>) -> List<String>:
  match xs:
    case Nil{}:
      ["-"]
    case Con{h, t}:
      files(t)

def status.ok(ok: Bool) -> IO(Unit):
  match ok:
    case True{}:
      IO.pure(Unit, Unit{})
    case False{}:
      IO.exit(1)

# b3sum exits 1 when any file failed.
def status(+n: U32) -> IO(Unit):
  status.ok(U32.is_eq(n, 0))

def main() -> IO(Unit):
  do IO<Unit>:
    args : List<String> <- IO.args()
    n : U32 <- IO.thread_count()
    files : F.Files <- F.B3IO.load(rest(args), n)
    bad : U32 <- F.B3IO.emit(hash(files))
    status(bad)
