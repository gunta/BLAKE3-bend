---
name: migrate-to-turboblake-rust
description: Move a Rust project from the blake3 crate to turboblake, the drop-in that hashes big inputs on every CPU core (and the GPU). Use when the user asks to speed up BLAKE3 hashing, switch to turboblake, or replace the blake3 crate in Cargo.toml, including for a dependency that pulls blake3 in.
---

# Migrate a Rust project to turboblake

turboblake is the official `blake3` crate (same version line, 1.8) with one change: once
an update is big enough, the subtree is hashed on every CPU core by a Bend2 engine
instead of on one. The library is still named `blake3`, so `use blake3::…` compiles
unchanged and every output is byte-for-byte BLAKE3. Small inputs run upstream's code.

## 1. Find what uses BLAKE3

```bash
grep -rn --include=Cargo.toml -E '^\s*blake3\b|blake3\s*=' .
grep -rln --include=*.rs 'blake3::' . | head -50
cargo tree -i blake3 -e normal 2>/dev/null   # who depends on it, directly or not
```

Note which features the project enables on `blake3` (`rayon`, `mmap`, `serde`, `zeroize`,
`traits-preview`, `std`, `no_avx512`…). turboblake has the same features.

## 2. Swap the dependency

**Direct dependency** (the project's own code calls `blake3::`): in each `Cargo.toml`,
replace the `blake3` line and keep its features. `package = "turboblake"` keeps the
dependency's name, so no `use` line changes:

```toml
# was: blake3 = { version = "1.8", features = ["rayon", "mmap"] }
blake3 = { package = "turboblake", version = "1.8", default-features = false, features = ["std", "rayon", "mmap"] }
```

`default-features = false, features = ["std"]` leaves out turboblake's command line and its
dependencies; add back whatever upstream features the project used. A workspace that
declares `blake3` under `[workspace.dependencies]` changes it there once.

**Only a dependency uses it** (iroh, bao, a database…): Cargo cannot rename a crate inside
someone else's graph, so patch in a copy named `blake3`:

```bash
git clone --depth 1 --branch turboblake-v{{version}} https://github.com/gunta/turboblake /tmp/turboblake
TURBOBLAKE_NAME=blake3 /tmp/turboblake/bend/rust/gen.sh vendor/blake3   # needs python3; commit vendor/blake3
```

```toml
# the workspace root's Cargo.toml
[patch.crates-io]
blake3 = { path = "vendor/blake3" }
```

Then `cargo update -p blake3` and check `cargo tree -i blake3` shows the path version.
The patch only applies if the graph's `blake3` requirement accepts 1.8.x; if a crate pins
an older major, say so instead of forcing it.

## 3. Code

Nothing to change. Optional, where it helps:

- `Hasher::update_rayon` still works; turboblake takes the part it beats rayon on.
- `Hasher::update_mmap_rayon` / `update_mmap` (feature `mmap`) for files.
- GPU memory, if the project has it: `unsafe { hasher.update_cuda(ptr, len, stream) }`,
  `unsafe { hasher.update_metal(buffer, offset, len) }`, and `blake3::gpu::backend()` says
  which runs. Do not add GPU code the project does not need.

## 4. Verify

```bash
cargo build && cargo test
```

Then check outputs against the official vectors (input: bytes `i % 251`):

```rust
assert_eq!(blake3::hash(b"").to_hex().as_str(),
    "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262");
let input: Vec<u8> = (0..1024u32).map(|i| (i % 251) as u8).collect();
assert_eq!(blake3::hash(&input).to_hex().as_str(),
    "42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7");
```

To see the engine take a big input, run the program with `TURBOBLAKE_TRACE=1` and hash
something over a few MiB: it prints its calibration and jobs to stderr.

## Know before you ship

- Building needs **clang** (the engine is C emitted by Bend2). Without it, and on Windows,
  the crate builds as upstream's and prints a warning: still correct, just not faster.
  CI images may need `apt-get install clang`.
- `no_std` builds are upstream's code.
- Run-time switches: `TURBOBLAKE=0` turns the engine off, `TURBOBLAKE_THREADS=<n>` caps it,
  `TURBOBLAKE_GPU=0` turns the GPU off; `TURBOBLAKE_NO_GPU=1` at build time leaves it out.
- It pays off from about 256 KiB per update; for many small hashes, expect upstream's speed.
- Rolling back is reverting the `Cargo.toml` lines (or removing the `[patch]`).

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3.
Docs: https://gunta.github.io/turboblake/install/rust/
