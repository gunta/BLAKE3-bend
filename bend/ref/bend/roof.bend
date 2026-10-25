# Bend rooflines: the GPU tree of hash1! (16384 leaves of 64 chunks at
# 1 GiB) with a leaf that only loads (B3.ld, XOR of every word) or only
# compresses (1024 compressions from registers, no reads), or hashes.
# usage: bend/build.sh bend/ref/bend/roof.bend && bend/ref/bend/build/roof <reps> <mode>
# (mode 0 load, 1 alu, 2 hash; 1 GiB of bench/mem.bend's data, warm)
import Base
import ../../blake3.bend as B3

def Clock.us() -> IO(Nat):
  import "../../effs/clock.c"
  import "../../effs/clock.js"

def fill(n: Nat, a: Array<U32>, +j: U32) -> Array<U32>:
  match n:
    case 0n:
      a
    case 1n+p:
      a[j] <- ((j * 2654435761 : U32) + 12345 : U32)
      fill(p, a, (j + 1 : U32))

def x16(m: B3.M16, +acc: U32) -> U32:
  match m:
    case B3.M16{m0, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13, m14, m15}:
      (acc .^. m0 .^. m1 .^. m2 .^. m3 .^. m4 .^. m5 .^. m6 .^. m7 .^. m8 .^. m9 .^.
        m10 .^. m11 .^. m12 .^. m13 .^. m14 .^. m15 : U32)

# n more blocks after the one in r, which was read at word w.
def rd.go(n: Nat, r: Array<U32> & B3.M16, +w: U32, +acc: U32) -> Array<U32> & U32:
  match n:
    case 0n:
      (a, m) = r
      (a, x16(m, acc))
    case 1n+p:
      (a, m) = r
      +w2 = (w + 16 : U32)
      rd.go(p, B3.ld(a, w2), w2, x16(m, acc))

def rd.fin(r: Array<U32> & U32) -> U32:
  (a, x) = r
  _ = a
  x

def alu.go(n: Nat, cv: B3.CV, +m: B3.M16, +t: U32) -> B3.CV:
  match n:
    case 0n:
      cv
    case 1n+p:
      alu.go(p, B3.compress(cv, m, t, 0, 64, 0), m, (t + 1 : U32))

def h0(cv: B3.CV) -> U32:
  match cv:
    case B3.CV{x0, x1, x2, x3, x4, x5, x6, x7}:
      x0

def leaf.b(b: Bool, a: Array<U32>, +c: U32) -> U32:
  match b:
    case True{}:
      _ = a
      +m = {B3.M16{c, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15} : B3.M16}
      h0(alu.go(1024n, B3.IV(), m, c))
    case False{}:
      h0(B3.g.fin(B3.g64(a, c, c, 0)))

def leaf.a(b: Bool, +mode: U32, a: Array<U32>, +c: U32) -> U32:
  match b:
    case True{}:
      +w = (c << 8n : U32)
      rd.fin(rd.go(1023n, B3.ld(a, w), w, 0))
    case False{}:
      leaf.b(U32.is_eq(mode, 1), a, c)

# 2^k leaves of 64 chunks from chunk c.
def tree(+k: Nat, aa: Array<U32> & Array<U32>, +c: U32, +mode: U32) -> U32:
  match k:
    case 0n:
      (a1, a2) = aa
      _ = a2
      leaf.a(U32.is_eq(mode, 0), mode, a1, c)
    case 1n+p:
      (a1, a2) = aa
      +h = (64 << p : U32)
      l r = tree(p, Array.fork(U32, a1), c, mode) tree(p, Array.fork(U32, a2), (c + h : U32), mode)
      (l .^. r : U32)

def run(a: Array<U32>, +mode: U32) -> U32:
  tree!(14n, Array.fork(U32, a), 0, mode)

def rep(n: Nat, +mode: U32, aa: Array<U32> & Array<U32>) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      (a, b) = aa
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        x : U32 = run(a, mode)
        t1 : Nat <- Clock.us()
        IO.print("us " ++ Nat.show(Nat.sub(t1, t0)) ++ " mode " ++ U32.show(mode) ++ " " ++ U32.show(x))
        rep(p, mode, Array.fork(U32, b))

def num(s: String, +dflt: U32) -> U32:
  Maybe.default(&2, U32, U32.read(s), dflt)

def go(xs: List<String>) -> IO(Unit):
  match xs:
    case Con{_, Con{r, Con{m, _}}}:
      a = fill(U32.to_nat((1 << 28n : U32)), Array.new(U32, 28n, 0), 0)
      rep(U32.to_nat(num(r, 5)), num(m, 0), Array.fork(U32, a))
    case _:
      IO.print("usage: roof <reps> <mode>")

def main() -> IO(Unit):
  do IO<Unit>:
    args : List<String> <- IO.args()
    go(args)
