# Daemon benchmark on the GPU: start once, then hash the same files round
# after round as bench/daemon.bend does, but on the GPU: the loader reads the files
# into the GPU's heap (a Metal buffer cannot take a file mapping) and the
# whole Files tree runs in one bang. Start-up, and the Metal heap's set-up,
# is paid once. Run with +RTS --gpu <heap> -RTS for big inputs.
# Prints "us <round microseconds> fold <xor of all hash words>" per round.
# usage: ./daemon <rounds> FILE...
import Base
import ../blake3.bend as B3
import ../b3io.bend as F

def Clock.us() -> IO(Nat):
  import "../effs/clock.c"
  import "../effs/clock.js"

# The bang sits in a pure def: inside a do block it would make the device
# own the tree (shaders guide).
def gpu(t: F.Files) -> F.Out:
  F.hashg!(t)

def round(n: Nat, +threads: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      do IO<Unit>:
        t0 : Nat <- Clock.us()
        files : F.Files <- F.B3IO.again(threads)
        x : U32 <- F.B3IO.fold(gpu(files))
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
