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

# The parts of a progressive load, each hashed while the next ones are
# still opening; the folds of the parts XOR into the round's fold.
def parts(n: Nat, +k: U32, +acc: U32) -> IO(U32):
  match n:
    case 0n:
      IO.pure(U32, acc)
    case 1n+p:
      do IO<U32>:
        files : F.Files <- F.B3IO.again_take(k)
        x : U32 <- F.B3IO.fold(F.hash(files))
        parts(p, (k + 1 : U32), (acc .^. x : U32))

def round(n: Nat, +threads: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        np : U32 <- F.B3IO.again_start(threads)
        x : U32 <- parts(U32.to_nat(np), 0, 0)
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
