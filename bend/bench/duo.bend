# CPU + GPU on one input at once, in two processes (see split.bend).
#   duo +RTS --gpu off -RTS <d> <reps> <j> <plan> <lv> 0   the CPU side, the leader
#   duo <d> <reps> <j> <plan> <lv> 1                       the GPU side
# Both fill the 2^d words of bench/mem.bend (so the digest is mem's). Each
# round the leader starts the GPU side, hashes its own share on the CPU pool,
# takes the GPU's CVs and folds the root, and prints the round's
# microseconds with the digest and when its own share was done; the GPU side
# prints its own. bench/duo.py starts the pair.
import Base
import ../blake3.bend as B3
import ../hash.bend as H
import ../split.bend as S

def Clock.us() -> IO(Nat):
  import "../effs/clock.c"
  import "../effs/clock.js"

def Duo.open(lead: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.ready(r: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.go(r: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.wait(r: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.put(i: U32, w0: U32, w1: U32, w2: U32, w3: U32, w4: U32, w5: U32,
  w6: U32, w7: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.done(r: U32, n: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.await(r: U32, x: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def Duo.get(i: U32) -> IO(U32):
  import "../effs/duo.c"
  import "../effs/duo.js"

def fill(n: Nat, a: Array<U32>, +j: U32) -> Array<U32>:
  match n:
    case 0n:
      a
    case 1n+p:
      a[j] <- ((j * 2654435761 : U32) + 12345 : U32)
      fill(p, a, (j + 1 : U32))

type Cfg is Data:
  Cfg{d: U32, reps: U32, j: U32, plan: U32, lv: U32, gpu: U32}

def num(s: String, +dflt: U32) -> U32:
  Maybe.default(&2, U32, U32.read(s), dflt)

def cfg(xs: List<String>) -> Cfg:
  match xs:
    case Con{_, Con{d, Con{r, Con{j, Con{p, Con{l, Con{g, _}}}}}}}:
      Cfg{num(d, 28), num(r, 3), num(j, 2), num(p, 3), num(l, 6), num(g, 0)}
    case _:
      Cfg{28, 3, 2, 3, 6, 0}

def gpu(+j: Nat, a: Array<U32>, +nch: U32, +plan: U32, +lv: U32) -> List<B3.CV>:
  H.side.g!(j, a, nch, 1024, plan, lv)

def cpu(+j: Nat, a: Array<U32>, +nch: U32, +plan: U32) -> List<B3.CV>:
  H.side.c(j, a, nch, 1024, plan)

# The share, and a word of it (0 if it is empty) for Duo.await to wait on.
def share(xs: List<B3.CV>) -> List<B3.CV> & U32:
  match xs:
    case Nil{}:
      ([], 0)
    case Con{h, t}:
      match h:
        case B3.CV{+w0, w1, w2, w3, w4, w5, w6, w7}:
          (B3.CV{w0, w1, w2, w3, w4, w5, w6, w7} <> t, w0)

def send(xs: List<B3.CV>, +i: U32) -> IO(U32):
  match xs:
    case Nil{}:
      IO.pure(U32, i)
    case Con{h, t}:
      match h:
        case B3.CV{w0, w1, w2, w3, w4, w5, w6, w7}:
          do IO<U32>:
            _ : U32 <- Duo.put(i, w0, w1, w2, w3, w4, w5, w6, w7)
            send(t, (i + 1 : U32))

def recv(n: Nat, +i: U32) -> IO(List<B3.CV>):
  match n:
    case 0n:
      IO.pure(List<B3.CV>, [])
    case 1n+p:
      +b = (i * 8 : U32)
      do IO<List<B3.CV>>:
        w0 : U32 <- Duo.get(b)
        w1 : U32 <- Duo.get((b + 1 : U32))
        w2 : U32 <- Duo.get((b + 2 : U32))
        w3 : U32 <- Duo.get((b + 3 : U32))
        w4 : U32 <- Duo.get((b + 4 : U32))
        w5 : U32 <- Duo.get((b + 5 : U32))
        w6 : U32 <- Duo.get((b + 6 : U32))
        w7 : U32 <- Duo.get((b + 7 : U32))
        rest : List<B3.CV> <- recv(p, (i + 1 : U32))
        return B3.CV{w0, w1, w2, w3, w4, w5, w6, w7} <> rest

# One round of the leader: the CPU's share is an argument of round.fin, so
# it is hashed after the GPU side has started.
def round.fin(cx: List<B3.CV> & U32, +t0: Nat, +r: U32, +j: Nat, +plan: U32,
  +nch: U32) -> IO(Unit):
  (c, x) = cx
  do IO<Unit>:
    tc : Nat <- Clock.us()
    +k : U32 <- Duo.await(r, x)
    g : List<B3.CV> <- recv(U32.to_nat(k), 0)
    h : B3.CV = S.root(j, nch, plan, g, c)
    t1 : Nat <- Clock.us()
    IO.print("us " ++ Nat.show(Nat.sub(t1, t0)) ++ " gpu " ++ U32.show(k) ++ " " ++ B3.hex(h) ++ " cpu_us " ++ Nat.show(Nat.sub(tc, t0)))

def round(+r: U32, +j: Nat, +plan: U32, a: Array<U32>, +nch: U32) -> IO(Unit):
  do IO<Unit>:
    _ : U32 <- Duo.ready(r)
    t0 : Nat <- Clock.us()
    _ : U32 <- Duo.go(r)
    round.fin(share(cpu(j, a, nch, plan)), t0, r, j, plan, nch)

def lead(n: Nat, +r: U32, +j: Nat, +plan: U32, aa: Array<U32> & Array<U32>,
  +nch: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      (a, b) = aa
      do IO<Unit>:
        round(r, j, plan, a, nch)
        lead(p, (r + 1 : U32), j, plan, Array.fork(U32, b), nch)

# The follower's rounds.
def follow(n: Nat, +r: U32, +j: Nat, +plan: U32, +lv: U32,
  aa: Array<U32> & Array<U32>, +nch: U32) -> IO(Unit):
  match n:
    case 0n:
      IO.pure(Unit, Unit{})
    case 1n+p:
      (a, b) = aa
      do IO<Unit>:
        _ : U32 <- Duo.wait(r)
        +t0 : Nat <- Clock.us()
        g : List<B3.CV> = gpu(j, a, nch, plan, lv)
        k : U32 <- send(g, 0)
        _ : U32 <- Duo.done(r, k)
        t1 : Nat <- Clock.us()
        IO.print("gpu_us " ++ Nat.show(Nat.sub(t1, t0)))
        follow(p, (r + 1 : U32), j, plan, lv, Array.fork(U32, b), nch)

def go.pick(b: Bool, +reps: U32, +j: Nat, +plan: U32, +lv: U32,
  aa: Array<U32> & Array<U32>, +nch: U32) -> IO(Unit):
  match b:
    case True{}:
      do IO<Unit>:
        _ : U32 <- Duo.open(0)
        follow(U32.to_nat(reps), 1, j, plan, lv, aa, nch)
    case False{}:
      do IO<Unit>:
        _ : U32 <- Duo.open(1)
        lead(U32.to_nat(reps), 1, j, plan, aa, nch)

def go(c: Cfg) -> IO(Unit):
  match c:
    case Cfg{+d, reps, j, plan, lv, gpu}:
      a = fill(U32.to_nat((1 << U32.to_nat(d) : U32)), Array.new(U32, U32.to_nat(d), 0), 0)
      go.pick(U32.is_eq(gpu, 1), reps, U32.to_nat(j), plan, lv, Array.fork(U32, a),
        (1 << U32.to_nat((d - 8 : U32)) : U32))

def main() -> IO(Unit):
  do IO<Unit>:
    args : List<String> <- IO.args()
    go(cfg(args))
