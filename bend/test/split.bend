# The CPU + GPU split (split.bend) on the official test-vector inputs: for
# every input of two chunks or more and every plan below, both shares (the
# GPU's tree run here on the CPU pool, no bang) folded by S.root. Prints one
# "len hash" line per case; test/check.py compares them with the JSON.
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

def main() -> IO(Unit):
  run([1025, 2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168,
    7169, 8192, 8193, 16384, 31744, 102400])
