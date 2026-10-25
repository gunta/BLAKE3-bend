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
