# ADR 0015: The trees that run, proven for every input

Date: 2026-10-26
Status: accepted

## Context

ADRs 0007 and 0010 proved the 8-lane lanes, the outboard tree and the tree
shapes for every input, but the trees that hash were covered by known
answers only: 13 official vectors of at most 8193 bytes, through code the
checker computes at ~0.6 s a compression. The site's "What is not proven"
list said so: Leaf32, g16 and g64 were left to the runtime vectors, the
loaders to the known answers ("a read of a symbolic array is stuck"), and
`tree1.digits` tied blake3.bend's split rule to the tree model only up to
1,024 chunks, by computation. The streaming laws (ADR 0010) were about a
model of b3io's merge stack (Nat counts, no ROOT flag), since b3io.bend
imports the effects and Array.fork and so cannot be named by a law. The
user asked whether those parts could be proven too.

Not all of it can. What the checker cannot see stays trusted: the C that
moves bytes, Bend's compiler and runtime, Array.fork's sharing, and the
hardware. Everything written in Bend that the command line and the
library run can be.

## Decision

Prove each tree that runs equal to blake3.bend's scalar tree (`tree1`, one
chunk at a time) for every array and every span, and the scalar tree equal
to BLAKE3's tree, in generated proof modules under `bend/proof/`
(`tools/proofs/`, written by `tools/gen_laws.py`):

| law | for every | module |
|-----|-----------|--------|
| `cpu.at`, `cpu.hash` | array and span: the CPU's 8-lane tree (`hash.at`, `hash`) is `tree1` | `cpu.bend` (109 lemmas) |
| `gpu.at`, `gpu.hash` | array and span: the GPU's tree (`hash1.at`, `hash1`: flat 4-, 16-, 64-chunk leaves, strided lanes) is `tree1` | `gpu.bend` (35) |
| `keyed.at` | array, span, key and mode flag: the keyed 8-lane tree (`hash8.at.k`, the library's keyed and derive-key path) is the scalar keyed tree (`hash.at.k`) | `keyed.bend` (53) |
| `tree1.digits` | chunk count: `tree1`'s split rule is the digit rule of the tree model (was: 1 to 1,024 chunks, by computation) | `spec.bend` |
| `ref.spec`, `cpu.spec`, `gpu.spec`, `keyed.spec` | array and span: the trees compute `ev(tree(digits(depth, nch - 1)))`, BLAKE3's left-full tree over the chunks, each leaf a chunk and each node a parent (keyed: with the key and the flag) | `spec.bend` (48) |
| `share.fork` | array: the laws' copy of the input is Array.fork's own body, `(a, a)` | `cpu.bend` |
| `stream.hash` | segment count and every CV the reads answer: the loop b3io runs on a streamed file (stack.bend's `stk.go`) answers BLAKE3's tree over the segments' CVs, ROOT on the top parent | `PROOF.bend` (27 lemmas) |

`words.bend` (95 lemmas) holds the arithmetic: U32 as Nat while it fits,
comparisons, carries, shifts and powers of two, each an induction over
the bits. Every law above holds for both words of the chunk counter: the
span's base `cb` and its high word `hi` (ADR 0014). The low word is added
with no carry, so the spec laws' counters are BLAKE3's 64-bit ones for
every span inside a 2^32-chunk block, which every span that runs is
(`span.nocarry`, ADR 0014's follow-up). The gate is 40 laws and 412
lemmas (41 laws with `span.nocarry`).

### How

- **Reads.** A read of a symbolic array is stuck, but the array's shape is
  not: `dup.w` splits an array into two copies proven equal to it (an
  induction on `ALeaf`/`ANode`), `tr` moves a fact about a copy back, and
  a proof that reads one array many times takes a bundle of copies
  (`Wits`, `Bun`). With that, `ld` and `ld8` hand their array back for
  every array, and lane l of `ld8` is the scalar block of chunk l.
- **CPU tree** (`cpu.tree`): lane l of the 8-lane chunk loop is chunk
  c + l's scalar chain, a 32-chunk leaf is `tree1` over its chunks, and
  node by node `tree8` takes `tree1`'s split exactly where `tree1` does,
  with `TN(c) + TN(n) <= TN(nch)` carried down the tree through the U32
  values. The node kind is computed from a U32 copy of the depth, so its
  decisions (big, whole and full, depth 5, depth 3) are parameters with
  their equations, and the induction matches them.
- **GPU tree** (`gpu.tree`, eight node kinds): `g4`, `g16`, `g64` are
  chains of four under parents; a strided lane (`quad`) is four 16-chunk
  subtrees st chunks apart, and a fork of 2^r lanes (`qt`, induction on r)
  is four subtrees of 16 << r chunks, each join pairing its halves' groups
  into the next level's subtrees. A GQuad node is `tree1` halved twice; at
  q = 26 (2^32 chunks) the node cannot occur, and the proof says why.
- **Depth bound.** `nch - 1 < 2^depth(nch)` for every U32, from
  `U32.log2`'s binary search (`lg.bound`: x is v shifted down b, and
  x < 2^(2^k), then v shifted down 1 + the result is 0).
- **Keyed tree**: `keyed.bend` is `cpu.bend` and `spec.bend` transformed,
  not written twice (`tools/proofs/keyed.py`): each default-mode call is
  its `.k` twin, the key is written as its eight words so `key8` unfolds
  as `IV8` does, the mode flag is or-ed into every compression's flags, and
  `k0..k7, kf` are threaded through the lemmas that then need them; the
  others are cpu.bend's and spec.bend's, referenced as `C.` and `S.`. It
  checked the first time.
- **The counter's high word.** ADR 0014 gave every counter-taking def in
  blake3.bend a `hi` beside its counter, down to `compress8` and
  `compress`'s second counter word. `tools/proofs/hi.py` threads it
  through the generated proofs, as `keyed.py` threads the key: every call
  of such a def gets `hi` at its place (`compress`'s 0 becomes `hi`), a
  lemma whose statement then mentions `hi` takes it as its last parameter,
  and one whose statement does not (its counter fixed by an entry point)
  passes 0. It runs on cpu.bend, then gpu.bend and spec.bend (which call
  cpu.bend's lemmas), and keyed.bend is built from the results. It
  checked the first time; only the laws and keyed.py's own lemmas were
  edited by hand.
- **Streaming.** b3io's merge stack moved to `stack.bend`, which imports
  only blake3.bend. Its loop, `stk.go`, takes the segment reads as a
  template (`~rd`): b3io passes its read-and-hash (`stream.seg`), the law a
  pure read from a list of CVs, and both compile the same loop. The proof
  maps the model's stack of Trees onto the real stack of CVs and shows
  every step commutes with the map: `pop2`, `lazy` (the U32 `n & 1` and
  `n >> 1` are the model's parity and half), `fin` (it flags the top parent
  ROOT, which the model leaves out), and the IO loop itself, rewritten
  under IO's continuation (`R => k => ...`); the U32 counter does not wrap
  while segments remain. Then `stream.shape` and `stream.order` make the
  model's tree BLAKE3's tree over the segments, in order.

## Results

`bend/prove.sh`: ALL PROOFS CHECK in 3:26 on the M5 Pro (244 s user;
the machine's load was not controlled). That is shorter than the 4:10 the
gate took with only the CPU proof added, because `tree1.digits` no longer
computes 1,024 trees. Without the known answers (a scratch copy with the
`kat.*` laws stripped) the rest checks in 41 s, ~12 s of it the keyed
module. With `stream.hash` added the gate took 3:41 (259 s user, load 5-7)
and the stripped copy 58 s (load ~7). Merged with ADR 0014's high word, the
gate takes 4:12 (284 s user, load 8-10); the stripped copy 54 s. The generated modules are
large (cpu.bend 476 KB, keyed.bend 518 KB, gpu.bend 238 KB) because each
rewrite states its motive in full; they are build products of
`tools/proofs/`.

## What is not proven

- **Array.fork.** The code passes `~fork` (Array.fork, `@unsafe`); the laws
  pass `~share` (Array.clone). `share.fork` proves the laws' copy is
  Array.fork's own body, `(a, a)`; that the runtime may then share one
  buffer is trusted.
- **The compression function.** `compress` (the rounds and G) is pinned by
  the official vectors and the `schedule` law. There is no second
  description of BLAKE3's compression in Bend to prove it against.
- **A big file's parts.** How the loader cuts a file into 1 GiB parts and
  reads them is the loader's (`effs/load.c`): `stream.hash` holds for
  every CV the reads answer, and that read k hands over segment k's bytes
  and chunk offset (its CV is then `hash.at`, the proven CPU tree) is the
  loader's part. b3io's own glue is not named by a law
  either: `stream.seg` (read, then `hash.at`), and `stream.pick`, which
  sends a one-segment stream to `stream.one` (hashed with ROOT).
- **Outside Bend.** The C that moves bytes (`effs/load.c`, `effs/emit.c`,
  the library's hook in the official C), the native Metal and CUDA kernels
  (ADR 0013), the CPU + GPU split in `split.bend` (bench code), and Bend's
  compiler, runtime and checker. `bend PROOF.bend --verdict` (the Lean
  kernel) still needs Lean v4.34.0.
- **Extended output.** `root.out` and the root defs in blake3.bend have no
  caller that ships: the library's XOF is the official C.

## Consequences

- The site's proofs section lists the new laws and the shorter "not
  proven" list; `bend/README.md` has the counts.
- A change to blake3.bend's trees now fails the gate unless its proof is
  updated: the generators in `tools/proofs/` follow the code's shape (a
  new node kind is a new case in `cpu.tree` or `gpu.tree`).
- A new def that takes the counter needs its place for `hi` in `hi.py`'s
  table, or its calls keep the old arity and the gate fails.
- Moving the stack changes the engine's C, so `bend/lib/csrc`, the Rust
  crate's copy and the Go module's C and macOS objects are regenerated;
  they also pick up `ld8` as eight scalar loads (ab5b899), which they had
  not followed yet. Against master's engine (the old `ld8`, with `hi`) the
  merged one hashes the same: one core, 64 MiB, 24.00 ms against 23.93
  (and 23.97 with the old `ld8` put back); all cores, 1 GiB, 28.54 ms
  against 28.94 (`bench/mem.bend`, load ~9). The Go Linux objects are
  built on Modal (`bench/modal_linux.py --steps go`) and still hold an
  earlier engine, which hashes the same.
