# In-memory throughput: fills 2^d words, then hashes them `reps` times on the
# CPU pool (mode 0) or the GPU (mode 1), printing each run's microseconds.
# usage: ./mem +RTS ... -RTS <d> <reps> <mode>
import Base
import ../blake3.bend as B3

def Clock.us() -> IO(Nat):
  import "../effs/clock.c"
  import "../effs/clock.js"

def fill(n: Nat, a: Array<U32>, +j: U32) -> Array<U32>:
  match n:
    case 0n:
      a
    case 1n+p:
      a[j] <- ((j * 2654435761 : U32) + 12345 : U32)
      fill(p, a, (j + 1 : U32))

type Cfg is Data:
  Cfg{d: U32, reps: U32, mode: U32}

def num(s: String, +dflt: U32) -> U32:
  Maybe.default(&2, U32, U32.read(s), dflt)

def cfg(xs: List<String>) -> Cfg:
  match xs:
    case Con{_, Con{d, Con{r, Con{m, _}}}}:
      Cfg{num(d, 28), num(r, 3), num(m, 0)}
    case _:
      Cfg{28, 3, 0}

def cpu(a: Array<U32>, +len: U32) -> B3.CV:
  B3.hash(a, len)

def gpu(a: Array<U32>, +len: U32) -> B3.CV:
  B3.hash!(a, len)

def run(b: Bool, a: Array<U32>, +len: U32) -> B3.CV:
  match b:
    case True{}:
      gpu(a, len)
    case False{}:
      cpu(a, len)

def rep(n: Nat, +mode: U32, aa: Array<U32> & Array<U32>, +len: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      (a, b) = aa
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        h : B3.CV = run(U32.is_eq(mode, 1), a, len)
        t1 : Nat <- Clock.us()
        IO.print("us " ++ Nat.show(Nat.sub(t1, t0)) ++ " bytes " ++ U32.show(len) ++ " " ++ B3.hex(h))
        rep(p, mode, Array.fork(U32, b), len)

def go(c: Cfg) -> IO(Unit):
  match c:
    case Cfg{+d, reps, mode}:
      a = fill(U32.to_nat((1 << U32.to_nat(d) : U32)), Array.new(U32, U32.to_nat(d), 0), 0)
      rep(U32.to_nat(reps), mode, Array.fork(U32, a), (4 << U32.to_nat(d) : U32))

def main() -> IO(Unit):
  do IO<Unit>:
    args : List<String> <- IO.args()
    go(cfg(args))
