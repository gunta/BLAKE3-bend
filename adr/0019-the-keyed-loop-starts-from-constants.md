# ADR 0019: The keyed loop starts from constants

Date: 2026-10-27
Status: accepted

## Context

BLAKE3's keyed hashing and key derivation hash the same tree as the default
mode, with the key in place of the IV as every chunk's first CV and a mode
flag in every compression. The engine runs them on an 8-lane keyed tree
(`gen_blake3.py`'s `gen_keyed8`, ADR 0012), the default tree's defs with the
key and the flag threaded through and its own copies of compress8.

Even with those copies, the keyed tree ran 2.2x slower per core than the
default tree: 256 MiB on one core in 194 ms against 98, and 1 GiB on every
core in 70-75 ms against 30-32. It made Python's `blake3(data, key=...)`
about twice as slow as PyPI's `blake3` with `max_threads=AUTO`, and ADR 0016
kept keyed subtrees off the engine on the rayon path (`flags == 0`).

The compiled code showed why. The default chunk loop (`group`, with `c8.go`
inlined) is 3,137 instructions, 2,050 of them full-width NEON. The keyed one
(`group.k`) was 9,852 with 122: clang's SLP vectorizer left it scalar, or
bundled its CVs in pairs of unrelated words. The two loops differ in one
place: `c8.go` starts its 64 CVs at `IV8()`, constants, and `c8.go.k` started
them at `key8(key)`, values known only at run time.

What we tried, each compiled and counted (`clang -S`, vector instructions per
function), the last three also in a standalone C copy of the loop that builds
in a second:

| shape of the keyed loop | vectorized |
|---|---|
| CVs start at `key8(key)` (as shipped) | no |
| without the mode flag in the flags word | no |
| key words through an opaque copy, one per word or one per lane | no |
| CVs start at constants, the key picked in the loop by a `match` or a select | no |
| the same, the key read from memory | no |
| CVs start at a constant key (a test, not BLAKE3) | yes |
| CVs start at constants, the key xor-ed in as a delta | yes |
| vectorizer options (`-slp-max-reg-size` 128 or 256, no horizontal reductions) | no, and the default tree gets worse |

## Decision

`c8.go.k` starts its CVs at `ZERO8()` and takes the key as a delta `d`, a
`CV`: each block's compression reads `mix8(cv, d)`, its CVs with lane word i
xor-ed with `d`'s word i. `group.k` passes the key as the first block's
delta, and every later block gets a zero delta. The loop's CVs start at
constants, as the default loop's do, and the key comes in through an xor,
which the vectorizer takes like any other operand.

The cost is 64 xors a block, 16 NEON instructions beside the compression's
~2,000. The keyed loop is now 3,387 instructions with 2,204 vector ops; built
for x86-64-v3 (the Go module's Linux and Intel Mac objects) it matches the
default loop as well (2,105 `ymm` instructions against 2,070).

The proofs (ADR 0015) follow the new shape. `tools/proofs/keyed.py` threads
the delta through the lemmas that unfold the loop (`loop.l*`, `c8.eta`), the
group lemmas start it from `ZERO8()` and the key, and two facts carry them
back to the default loop's proof: `mix8.zero` (a zero delta changes nothing)
and `zk` (a lane of the key xor-ed into zeros is the key), from two new word
lemmas proven over the bits, `u.xor_zero_l` and `u.xor_zero_r`.

## Measurements

Interleaved with the build before the change, Apple M5 Pro, the same digests:

| | before | after | default mode |
|---|---:|---:|---:|
| keyed, 256 MiB, one core | 194-212 ms | 105-119 ms | 97-105 ms |
| keyed, 1 GiB, every core | 70-75 ms | 33-36 ms | 30-38 ms |

Python, `blake3(data, key=key)` against PyPI's `blake3` 1.0.11 with
`max_threads=AUTO`, interleaved:

| | turboblake | `blake3`, AUTO |
|---|---:|---:|
| 16 MiB | 0.55-0.61 ms | 0.56-0.97 ms |
| 256 MiB | 7.5-7.7 ms | 7.2 ms |
| 1 GiB | 32.5-33.1 ms | 29.6-31.3 ms |

the same margins as the default mode's (ADR 0016).

## Consequences

- Keyed hashing and key derivation run at the default mode's speed in every
  binding that sends them to the engine: C, Python, Node, Go, and the Rust
  crate's serial `hash` and `update`.
- The Rust crate's `update_rayon` still keeps keyed subtrees on upstream's
  code (`flags == 0` in `bend.rs`, ADR 0016). With the gap gone, that gate is
  for a fresh race of keyed `update_rayon` against upstream to decide.
- A rule for the generator, beside ADR 0012's one caller per compress8: a
  chunk loop's CVs must start at constants. Anything known only at run time
  comes in through an operation inside the loop that the vectorizer can
  bundle, such as an xor, never as the loop's starting value or a choice
  between values.
- Checks: `ALL PROOFS CHECK`; libturboblake's 1495 checks (1525 with `--big`
  on Linux x86-64); the crate's upstream tests with every subtree on the
  engine; `go test`; the Node tests (official vectors and `@noble/hashes`);
  blake3-py's tests through the engine.
