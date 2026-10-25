# Daemon benchmark: start once, then hash the same files round after round,
# as a background sync service would, timing each round inside the process
# (open + map or read, hash, release), with no process start-up in it.
# Prints "us <round microseconds> fold <xor of all hash words>" per round.
# usage: ./daemon <rounds> FILE...
import Base
import ../blake3.bend as B3
import ../b3io.bend as F

def Clock.us() -> IO(Nat):
  import "../effs/clock.c"
  import "../effs/clock.js"

def round(n: Nat, +threads: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        files : F.Files <- F.B3IO.again(threads)
        x : U32 <- F.B3IO.fold(F.hash(files))
        F.B3IO.release()
        t1 : Nat <- Clock.us()
        IO.print("us " ++ Nat.show(Nat.sub(t1, t0)) ++ " fold " ++ U32.show(x))
        round(p, threads)

def args(xs: List<String>) -> U32 & List<String>:
  match xs:
    case Con{_, Con{r, paths}}:
      (Maybe.default(&2, U32, U32.read(r), 5), paths)
    case _:
      (0, Nil{})

def run(rp: U32 & List<String>) -> IO(Unit):
  (+rounds, paths) = rp
  do IO<Unit>:
    n : U32 <- IO.thread_count()
    k : U32 <- F.B3IO.keep(paths)
    round(U32.to_nat(rounds), n)

def main() -> IO(Unit):
  do IO<Unit>:
    xs : List<String> <- IO.args()
    run(args(xs))
