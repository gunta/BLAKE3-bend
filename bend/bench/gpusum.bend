# b3sum with the hashing on the GPU: the same loader and output as
# b3sum.bend, the Files tree hashed in one bang (b3io's hashg!), to check
# the GPU tree on real files against the official b3sum: the output must
# be byte-identical.
# Files must be in the page cache (a GPU heap cannot stream them).
# usage: ./gpusum +RTS --gpu <heap> -RTS FILE...
import Base
import ../b3io.bend as F

# The bang sits in a pure def (shaders guide).
def gpu(t: F.Files) -> F.Out:
  F.hashg!(t)

def args(xs: List<String>) -> List<String>:
  match xs:
    case Nil{}:
      []
    case Con{_, t}:
      t

def main() -> IO(Unit):
  do IO<Unit>:
    xs : List<String> <- IO.args()
    n : U32 <- IO.thread_count()
    files : F.Files <- F.B3IO.load(args(xs), n)
    bad : U32 <- F.B3IO.emit(gpu(files))
    IO.pure(Unit, Unit{})
