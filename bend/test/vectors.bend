# Hashes the official test-vector inputs (byte i is i % 251) and prints one
# "len hash" line per case; test/check.py compares them with the JSON.
import Base
import ../blake3.bend as B3

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

def one(+len: U32) -> String:
  a = fill(U32.to_nat(((len + 3 : U32) >> 2n : U32)), [0 : U32^15n], 0, len)
  U32.show(len) ++ " " ++ B3.hex(B3.hash(a, len))

def run(xs: List<&2, U32>) -> IO(Unit):
  match xs:
    case Nil{}:
      IO.pure(Unit, Unit{})
    case Con{x, rest}:
      do IO<Unit>:
        IO.print(one(x))
        run(rest)

def main() -> IO(Unit):
  run([0, 1, 2, 3, 4, 5, 6, 7, 8, 63, 64, 65, 127, 128, 129, 1023, 1024, 1025,
    2048, 2049, 3072, 3073, 4096, 4097, 5120, 5121, 6144, 6145, 7168, 7169,
    8192, 8193, 16384, 31744, 102400])
