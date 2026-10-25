# The CPU + GPU split (split.bend) on the official test-vector inputs: for
# every input of two chunks or more and every plan below, both shares (the
# GPU's tree run here on the CPU pool, no bang) folded by S.root. Prints one
# "len hash" line per case; test/check.py compares them with the JSON. Then
# bigger inputs, past the vectors, where the GPU's share at leaf level 6
# takes strided lanes (blake3.bend's GQuad): each split is compared with the
# CPU tree, "same len" or "DIFF len"; and the split by slices the same way.
import Base
import ../blake3.bend as B3
import ../hash.bend as H
import ../split.bend as S

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

def input(+len: U32) -> Array<U32>:
  fill(U32.to_nat(((len + 3 : U32) >> 2n : U32)), [0 : U32^15n], 0, len)

# One plan: j spine levels, the owner bits, the GPU's leaf level.
def one(+len: U32, +j: U32, +plan: U32, +lv: U32) -> String:
  +n = B3.chunks(len)
  +last = B3.tail(len, n)
  +jn = U32.to_nat(j)
  U32.show(len) ++ " " ++ B3.hex(S.root(jn, n, plan,
    H.side.g(jn, input(len), n, last, plan, lv),
    H.side.c(jn, input(len), n, last, plan)))

def plans(+len: U32, ps: List<&2, U32>) -> String:
  match ps:
    case Con{j, Con{p, Con{lv, rest}}}:
      one(len, j, p, lv) ++ "\n" ++ plans(len, rest)
    case _:
      ""

def run(xs: List<&2, U32>) -> IO(Unit):
  match xs:
    case Nil{}:
      IO.pure(Unit, Unit{})
    case Con{x, rest}:
      do IO<Unit>:
        IO.print(plans(x, [1, 0, 6, 1, 1, 6, 1, 2, 6, 1, 3, 2, 2, 5, 6, 2, 2, 4,
          3, 5, 2, 3, 10, 6, 4, 13, 4, 6, 42, 2, 9, 341, 6]))
        run(rest)

def cv.eq(x: B3.CV, y: B3.CV) -> Bool:
  match x y:
    case B3.CV{x0, x1, x2, x3, x4, x5, x6, x7} B3.CV{y0, y1, y2, y3, y4, y5, y6, y7}:
      U32.is_eq(x0, y0) && U32.is_eq(x1, y1) && U32.is_eq(x2, y2) &&
        U32.is_eq(x3, y3) && U32.is_eq(x4, y4) && U32.is_eq(x5, y5) &&
        U32.is_eq(x6, y6) && U32.is_eq(x7, y7)

def same.show(b: Bool) -> String:
  match b:
    case True{}:
      "same "
    case False{}:
      "DIFF "

def input.big(+len: U32) -> Array<U32>:
  fill(U32.to_nat(((len + 3 : U32) >> 2n : U32)), [0 : U32^18n], 0, len)

# A big input (2^18 words of the vector pattern, a len-byte prefix): the
# split with the GPU's share at leaf level 6 against the CPU tree.
def big(+len: U32, +j: U32, +plan: U32) -> String:
  +n = B3.chunks(len)
  +last = B3.tail(len, n)
  +jn = U32.to_nat(j)
  same.show(cv.eq(S.root(jn, n, plan, H.side.g(jn, input.big(len), n, last, plan, 6),
    H.side.c(jn, input.big(len), n, last, plan)), H.hash(input.big(len), len))) ++
    U32.show(len) ++ " j " ++ U32.show(j) ++ " plan " ++ U32.show(plan)

def bigs(xs: List<&2, U32>) -> IO(Unit):
  match xs:
    case Con{len, Con{j, Con{p, rest}}}:
      do IO<Unit>:
        IO.print(big(len, j, p))
        bigs(rest)
    case _:
      IO.pure(Unit, Unit{})

def run.vectors(u: Unit) -> IO(Unit):
  _ = u
  run([1025, 2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168,
    7169, 8192, 8193, 16384, 31744, 102400])

# A whole input of 2^(k+6) chunks split by slices, the GPU's first g of 16
# (its tree run here on the CPU pool), against the CPU tree.
def slices(+k: U32, +g: U32) -> String:
  +len = (65536 << U32.to_nat(k) : U32)
  +kn = U32.to_nat(k)
  same.show(cv.eq(S.slice.root(H.slice.g(kn, input.big(len), U32.to_nat(g)),
    H.slice.c(kn, input.big(len), g)), H.hash(input.big(len), len))) ++
    U32.show(len) ++ " slices " ++ U32.show(g)

def slicess(xs: List<&2, U32>) -> IO(Unit):
  match xs:
    case Con{k, Con{g, rest}}:
      do IO<Unit>:
        IO.print(slices(k, g))
        slicess(rest)
    case _:
      IO.pure(Unit, Unit{})

def main() -> IO(Unit):
  do IO<Unit>:
    run.vectors(Unit{})
    slicess([0, 1, 0, 15, 1, 8, 2, 13, 3, 3, 3, 12, 4, 1, 4, 13, 4, 15])
    bigs([131072, 1, 1, 131072, 1, 3, 132096, 1, 1, 262144, 2, 3, 263169, 2, 5,
      524288, 3, 7, 589825, 3, 5, 1048576, 2, 3, 1048575, 4, 13, 917504, 3, 3])
