# File input and output for b3sum
# ===============================
#
# B3IO.load reads a list of files, in parallel, straight into Array<U32>
# blocks (no byte lists), and answers them as a tree balanced by bytes, so
# a fork over it splits the hashing work evenly. B3IO.emit prints the hashes
# of an Out tree in one write. effs/load.c and effs/emit.c are the C sides:
# they move bytes, the hashing is blake3.bend.

import Base
import ./blake3.bend as B3

# The 1 GiB parts of a big file, in BLAKE3's left-full shape: a leaf is a
# span (see blake3.bend's hash.at) of 2^20 chunks, or fewer for the last.
type Segs is Type:
  SLeaf{arr: Array<U32>, cb: U32, nch: U32, last: U32}
  SNode{l: Segs, r: Segs}

type Files is Type:
  FNone{}
  FFile{arr: Array<U32>, len: U32, name: String}
  FSegs{segs: Segs, name: String}
  FErr{msg: String, name: String}
  FPair{l: Files, r: Files}

type Out is Data:
  ONone{}
  OHash{cv: B3.CV, name: String}
  OErr{msg: String, name: String}
  OPair{l: Out, r: Out}

def B3IO.load(paths: List<String>, threads: U32) -> IO(Files):
  import "./effs/load.c"
  import "./effs/load.js"

# Prints the hashes on stdout and the errors on stderr; answers the errors.
def B3IO.emit(o: Out) -> IO(U32):
  import "./effs/emit.c"
  import "./effs/emit.js"

# The XOR of every hash's words: a daemon's check, with nothing printed.
def B3IO.fold(o: Out) -> IO(U32):
  import "./effs/emit.c"
  import "./effs/emit.js"

# A daemon's loop: keep the paths once, load them again each round (with
# empty names), and release the mapped files once their hashes are out.
def B3IO.keep(paths: List<String>) -> IO(U32):
  import "./effs/load.c"
  import "./effs/load.js"

def B3IO.again(threads: U32) -> IO(Files):
  import "./effs/load.c"
  import "./effs/load.js"

def B3IO.release() -> IO(Unit):
  import "./effs/load.c"
  import "./effs/load.js"

# Outboards: a hash with its bao outboard pairs (see blake3.bend's OB).
type Obo is Data:
  BNone{}
  BHash{cv: B3.CV, ob: B3.OB, name: String}
  BErr{msg: String, name: String}
  BPair{l: Obo, r: Obo}

# Writes each file's outboard, in bao-tree's pre-order layout (64 bytes a
# pair, no size suffix), to dir/<base name>.obao; prints the hashes as
# b3sum does; answers the errors.
def B3IO.ob_write(o: Obo, dir: String) -> IO(U32):
  import "./effs/emit.c"
  import "./effs/emit.js"

# The XOR of every hash's words and every outboard pair's words.
def B3IO.ob_fold(o: Obo) -> IO(U32):
  import "./effs/emit.c"
  import "./effs/emit.js"

# Hashing
# -------

# A big file's parts hash in parallel, each a complete subtree but the
# last, and merge as BLAKE3's parents; only the top one is the root.
def segs(s: Segs, +rf: U32) -> B3.CV:
  match s:
    case SLeaf{a, cb, nch, last}:
      B3.hash.at(a, cb, nch, last, rf)
    case SNode{l, r}:
      x y = segs(l, 0) segs(r, 0)
      B3.parent(x, y, rf)

# Every file at once: the fork over the tree runs files in parallel, and
# each file's BLAKE3 tree is parallel too.
def hash(t: Files) -> Out:
  match t:
    case FNone{}:
      ONone{}
    case FFile{a, len, name}:
      OHash{B3.hash(a, len), name}
    case FSegs{s, name}:
      OHash{segs(s, B3.ROOT()), name}
    case FErr{msg, name}:
      OErr{msg, name}
    case FPair{l, r}:
      x y = hash(l) hash(r)
      OPair{x, y}

def segs.o(s: Segs, +rf: U32) -> B3.CV & B3.OB:
  match s:
    case SLeaf{a, cb, nch, last}:
      B3.hash.ob.at(a, cb, nch, last, rf)
    case SNode{l, r}:
      x y = segs.o(l, 0) segs.o(r, 0)
      B3.join.o(x, y, rf, True{})

def hash_ob.leaf(r: B3.CV & B3.OB, name: String) -> Obo:
  (cv, ob) = r
  BHash{cv, ob, name}

# hash, keeping every file's outboard.
def hash_ob(t: Files) -> Obo:
  match t:
    case FNone{}:
      BNone{}
    case FFile{a, len, name}:
      hash_ob.leaf(B3.hash.ob(a, len), name)
    case FSegs{s, name}:
      hash_ob.leaf(segs.o(s, B3.ROOT()), name)
    case FErr{msg, name}:
      BErr{msg, name}
    case FPair{l, r}:
      x y = hash_ob(l) hash_ob(r)
      BPair{x, y}
