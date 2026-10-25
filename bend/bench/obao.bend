# Writes the bao outboard iroh-blobs keeps for each file (bao-tree's
# pre-order layout, 16 KiB chunk groups) to DIR/<name>.obao and prints the
# hashes as b3sum does. bench/iroh's ob-check compares them with bao-tree.
# usage: ./obao DIR FILE...
import Base
import ../blake3.bend as B3
import ../b3io.bend as F

def args(xs: List<String>) -> String & List<String>:
  match xs:
    case Con{_, Con{d, paths}}:
      (d, paths)
    case _:
      (".", Nil{})

def run(dp: String & List<String>) -> IO(Unit):
  (dir, paths) = dp
  do IO<Unit>:
    n : U32 <- IO.thread_count()
    files : F.Files <- F.B3IO.load(paths, n)
    bad : U32 <- F.B3IO.ob_write(F.hash_ob(files), dir)
    IO.pure(Unit, Unit{})

def main() -> IO(Unit):
  do IO<Unit>:
    xs : List<String> <- IO.args()
    run(args(xs))
