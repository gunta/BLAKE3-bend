# Loads one file with B3IO.load, then hashes it `reps` times, printing each
# pass's microseconds: the first pass takes the page faults of a mapped file.
# usage: ./file <path> <reps>
import Base
import ../blake3.bend as B3
import ../hash.bend as H
import ../b3io.bend as F

def Clock.us() -> IO(Nat):
  import "../effs/clock.c"
  import "../effs/clock.js"

def rep(n: Nat, aa: Array<U32> & Array<U32>, +len: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      (a, b) = aa
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        h : B3.CV = H.hash(a, len)
        t1 : Nat <- Clock.us()
        IO.print("us " ++ Nat.show(Nat.sub(t1, t0)) ++ " " ++ B3.hex(h))
        rep(p, Array.fork(U32, b), len)

def go(t: F.Files, +reps: U32) -> IO(Unit):
  match t:
    case F.FFile{a, len, name}:
      rep(U32.to_nat(reps), Array.fork(U32, a), len)
    case _:
      IO.print("expected one readable file")

def args(xs: List<String>) -> List<String> & U32:
  match xs:
    case Con{_, Con{p, Con{r, _}}}:
      ([p], Maybe.default(&2, U32, U32.read(r), 3))
    case _:
      (Nil{}, 0)

def run(pr: List<String> & U32) -> IO(Unit):
  (paths, +reps) = pr
  do IO<Unit>:
    n : U32 <- IO.thread_count()
    t0 : Nat <- Clock.us()
    files : F.Files <- F.B3IO.load(paths, n)
    t1 : Nat <- Clock.us()
    IO.print("load us " ++ Nat.show(Nat.sub(t1, t0)))
    go(files, reps)

def main() -> IO(Unit):
  do IO<Unit>:
    xs : List<String> <- IO.args()
    run(args(xs))
