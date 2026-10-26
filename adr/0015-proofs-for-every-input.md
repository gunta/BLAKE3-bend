# ADR 0015: The trees that run, proven for every input

Date: 2026-10-26
Status: accepted

(0014 is taken by the 4 TiB branch, `claude/file-size-limit-4tib-a72dee`.)

## Context

ADRs 0007 and 0010 proved the 8-lane lanes, the outboard tree and the tree
shapes for every input, but the trees that hash were covered by known
answers only: 13 official vectors of at most 8193 bytes, through code the
checker computes at ~0.6 s a compression. The site's "What is not proven"
list said so: Leaf32, g16 and g64 were left to the runtime vectors, the
loaders to the known answers ("a read of a symbolic array is stuck"), and
`tree1.digits` tied blake3.bend's split rule to the tree model only up to
1,024 chunks, by computation. The user asked whether those parts could be
proven too.

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

`words.bend` (95 lemmas) holds the arithmetic: U32 as Nat while it fits,
comparisons, carries, shifts and powers of two, each an induction over
the bits. The gate is 38 laws and 385 lemmas.

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

## Results

`bend/prove.sh`: ALL PROOFS CHECK in 3:26 on the M5 Pro (244 s user;
the machine's load was not controlled). That is shorter than the 4:10 the
gate took with only the CPU proof added, because `tree1.digits` no longer
computes 1,024 trees. Without the known answers (a scratch copy with the
`kat.*` laws stripped) the rest checks in 41 s, ~12 s of it the keyed
module. The generated modules are
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
- **Streaming and a big file's parts.** `b3io.bend` imports the effects and
  Array.fork, so the stream laws are about a model of its merge stack (Nat
  counts, no ROOT flag on the last merge), and how the loader cuts a file
  into parts is the loader's. Moving `stk.*` into a proof-safe module would
  let the laws name them.
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
- The 4 TiB branch adds a high counter word to every compression; merging
  it means regenerating the proofs (the counters are terms in every lane
  and chain lemma), which the generators make mechanical.
