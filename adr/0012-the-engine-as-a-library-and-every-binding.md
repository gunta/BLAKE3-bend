# ADR 0012: The engine as a library, and a drop-in for every language

Date: 2026-10-26
Status: accepted

## Context

turboblake made `b3sum` fast, but most BLAKE3 runs inside programs: the Rust
crate, the C library, `blake3` on PyPI, `@noble/hashes` and the `blake3`
package on npm, `lukechampine.com/blake3` and `github.com/zeebo/blake3` in
Go. The goal: the whole library, with an adapter for each of those, so that
swapping one in is an install line and, at most, an import.

Two ways to get there:

- **A BLAKE3 per language on Bend.** Each binding would reimplement the
  incremental API (chunk state, CV stack, keyed hashing, key derivation,
  extended output, seeking) over Bend's tree. That is six reimplementations
  of the parts users touch, each one a place to get the spec wrong.
- **One hook in the official code.** BLAKE3 can be parallel in exactly one
  place: a complete subtree whose CV the incremental hasher is about to push.
  Upstream's C and Rust both reach it through one function,
  `compress_subtree_to_parent_node`. Hand that subtree to Bend and leave the
  rest to upstream's code.

We took the hook. Every binding then gets upstream's semantics unchanged, and
Bend runs every compression of every big subtree.

## Decision

### libblake3-bend: the official C library with one hook

`bend/lib/patch.py hook` adds one call at the top of
`compress_subtree_to_parent_node` in the official `c/blake3.c`:
`blake3_bend_subtree` (`bend/lib/blake3_bend.c`) takes subtrees past a size
threshold, cuts them into spans of at most 1 GiB (each a whole subtree), sends
them to the engine as one job, and merges the span CVs into the two child CVs
upstream expects. `blake3.h`, its symbols and the `blake3_hasher` layout are
unchanged, so programs relink and run.

The Rust crate `blake3-bend` is the official crate (1.8.7) with the same hook
in its Rust copy of that function (`src/bend.rs`, through `patch_crate.py`),
linking the same engine. Its library is still named `blake3`, so
`use blake3::…` compiles unchanged, and `[patch.crates-io]` can swap it under
a whole dependency graph.

### The engine: a Bend program that lives on its own thread

`bend/lib/engine.bend` is compiled by Bend2 to C with `main` renamed
(`-Dmain=b3e_bend_main`) and runs on a pthread for the life of the process.
`Eng.next` blocks on a job queue, Bend hashes every span of the job at once
(`H.hash.at`, the 8-lane tree of ADR 0002, or `H.hash8.at.k` for keyed hashing
and key derivation), and `Eng.done` hands the CVs back. `BEND_EMBED` patches
take out what a library must not do to its host: Bend's `SIGSEGV`/`SIGBUS`
handlers and its `SIGPIPE` ignore.

Keyed hashing and key derivation needed an 8-lane keyed tree
(`gen_blake3.py`'s `gen_keyed8`). Passing the key down the tree as an 8-lane
record crashed Apple clang's backend ("live register clobbered"), so the key
travels as one CV and is broadcast to lanes at the leaves.

The engine starts on the first big update. The threshold is calibrated then:
twice the measured round trip times the single-core rate, clamped to
64 KiB..64 MiB, about 256 KiB on an Apple M5 Pro (`BLAKE3_BEND_MIN`
overrides it).

### The heap, and whether the input is copied

Bend's arrays are addressed by a 40-bit location: anything it reads must lie
in an 8 TiB window past its heap's base. Where the caller's buffer already
lies in that window, the engine reads it in place.

- **Linux:** the heap is placed so the window covers the region where `mmap`
  (and so `malloc`) puts big buffers: no copy.
- **Go:** Go's heap sits near the top of the address space; the engine places
  its window over it from the first input's address (`b3e_hint`): no copy.
- **macOS:** every big allocation lies below 512 GiB, a range reserved for
  malloc where no heap can be mapped. Spans are copied, by helper threads one
  64 MiB block ahead, into two warm blocks of Bend's heap.

### The bindings

| language | package | replaces | how |
|---|---|---|---|
| C | libblake3-bend | the official C library | `bend/lib/build.sh` |
| Rust | `blake3-bend` (crates.io) | `blake3` | `blake3 = { package = "blake3-bend", … }` |
| Python | `turboblake` | `blake3` (PyPI) | blake3-py's own C extension (`c_impl`) on libblake3-bend, with a real `mmap` for `update_mmap`; module `blake3` |
| Node, Bun, Deno | `turboblake` | `@noble/hashes/blake3`, `blake3`, `@napi-rs/blake-hash` | a Node-API addon on libblake3-bend, both APIs from one package |
| browsers, workers | `turboblake/js` | `@noble/hashes/blake3`, `hash-wasm` | Bend's BLAKE3 emitted by Bend2's JS target |
| Go | `github.com/gunta/BLAKE3-bend/bend/go` (and `/zeebo`) | `lukechampine.com/blake3`, `github.com/zeebo/blake3` | cgo on libblake3-bend |

Two of these needed more than a wrapper:

- **Go.** cgo refuses the `-mllvm` flags the 8-lane compress needs
  (ADR 0002). The engine is compiled outside cgo and linked as prebuilt
  `engine_<os>_<arch>.syso` objects for darwin and linux on arm64 and amd64;
  elsewhere a build constraint falls back to `c_engine.c` at plain flags.
- **Browsers.** Bend2 has a C target and a JS target, no WebAssembly, and
  its C runtime needs pthreads and an 8 TiB `mmap` window. The JS target is
  Bend's own answer, so browsers get it: `bend/js/blake3.bend` (scalar
  compress, from `gen_blake3.py --scalar`, since the JS emitter overflows on
  `compress8`) emitted to `js/blake3.mjs`, with the incremental API in plain
  JavaScript around it. It is also the fallback when no C compiler is there
  at install time.

Each binding runs the test suite of the package it replaces where one exists:
upstream's Rust tests with the engine taking every subtree, blake3-py's tests,
1,495 checks of the C library against the official one in every mode, the
official vectors and random inputs against `@noble/hashes` in Node and in a
browser, and the official vectors plus both Go modules on random inputs.

## Measurements

One-shot hash of 1 GiB in memory, medians of interleaved runs, the same digest
from every BLAKE3 (`bend/bench/results/lang-*.json`, folded into results.json
by `bend/bench/collect.py`). Apple M5 Pro, 18 cores:

| language | turboblake | the packages it replaces |
|---|---|---|
| C | **38.7 ms** | official C 481 ms (one thread) |
| Rust | 37.8 ms | `blake3::hash` 507 ms; `update_rayon` **31.9 ms** |
| Python | 41.9 ms | `blake3` 505 ms; `max_threads=AUTO` **34.0 ms** |
| Node | **38.2 ms** | `@napi-rs/blake-hash` 482 ms, hash-wasm 964 ms, `@noble/hashes` 10.9 s |
| Bun | **46.7 ms** | `@napi-rs/blake-hash` 479 ms, hash-wasm 1.9 s, `@noble/hashes` 3.1 s |
| Go | **40.5 ms** | lukechampine 99.6 ms (every core), zeebo 1144 ms |
| Go, Linux x86-64 (Modal) | **23.9 ms** | lukechampine 57.4 ms, zeebo 392 ms |

Bun and Go on the Mac are from before the compress8 fix below (another
session held 11 cores when they re-ran), so they understate turboblake.
Bend's JS build hashes 1 GiB in 7.7 s on Node (21.8 s on Bun): slower than
`@noble/hashes` on Bun, faster on Node, and correct everywhere. It is for
where native code cannot go.

### Addendum: one caller per compress8

The first engine with both trees was 1.47x slower per core than b3sum's
Bend (606 against 412 ms per GiB on one core), in every binding. The keyed
tree called the default mode's `compress8` and `compress8.p`, so each had
two callers, and clang kept them out of line: a call with 196 flattened
arguments per eight blocks, where b3sum's single caller inlines and
vectorizes it (ADR 0002). The keyed tree now has its own copies
(`compress8.k`, `compress8.p.k`); one core is back to 403 ms per GiB, and
1 GiB through the library on every core went from about 45 ms to 34-38 ms.
The general rule for the generator: a program that holds two trees needs a
compress8 per tree.

## Consequences

- One engine, six ecosystems: a speed-up in `engine.bend` or `blake3.bend`
  reaches every binding with a rebuild.
- **The Mac's copy still costs the lead.** On a buffer already in the
  window the engine hashes 1 GiB in 28-31 ms, as fast as b3sum's Bend;
  through the library, with each span copied in, 34-38 ms. The official crate
  on rayon reads in place and gets about 30-32 ms, so it wins from 16 MiB up
  on the Mac (Rust's `update_rayon`, and blake3-py's `max_threads=AUTO`, which
  is that crate). Fewer copy threads or deeper staging measured no better.
  Aliasing the caller's pages into the window with `mach_vm_remap` instead
  of copying them is worse: the remap itself is 0.02 ms, but the first touch
  of each 16 KiB page faults (1 GiB hashed in 41.7 ms) and unmapping costs
  8 ms more.
- **AVX-512 wants 16 lanes.** On an x86-64 with AVX-512 the official crate's
  16-way kernel beats the 8-lane engine at 1 GiB (14.4 ms against 24.7 ms on
  Modal), though the engine wins at 64 MiB (1.7 against 4.6 ms). A 16-lane
  `compress16` vectorizes to `zmm` registers with
  `-mprefer-vector-width=512 -mllvm -slp-max-reg-size=1024`, but it cannot be
  the generator's `L = 16`: Bend keeps constructor and function arity in a
  byte, and compress16 would take about 388 flattened arguments (compress8
  takes 196). It needs another shape first.
- The Python and JavaScript packages are named `turboblake` for PyPI and
  npm but not published yet; the install page and READMEs install them from
  the repository until then. The Rust crates (`blake3-bend`, `turboblake`)
  are on crates.io.
- The site's /languages/ and /install/ pages read these results and this
  table of packages.
