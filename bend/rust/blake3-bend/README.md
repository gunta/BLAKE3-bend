# blake3-bend

The official [`blake3`](https://crates.io/crates/blake3) crate (1.8.7), with
one change: when an update reaches a big subtree, it is hashed on every core
by a [Bend2](https://bend-lang.com) engine instead of on one. Same API, same
library name (`blake3`), same output; upstream's own test suite passes with
the engine taking every subtree.

```toml
[dependencies]
blake3 = { package = "blake3-bend", version = "1.8" }
```

Your code keeps `use blake3::…`. `blake3::hash`, `Hasher::update`, and
`update_rayon` all go through the engine past a size it calibrates at the
first big input (about 256 KiB on an Apple M5 Pro), in every mode (keyed
hashing and key derivation too). Below that, and in `no_std` builds, it is
upstream's code.

To swap it in for every crate in a dependency graph (iroh, for example),
generate a copy named `blake3` and patch it in:

```bash
git clone https://github.com/gunta/BLAKE3-bend && BLAKE3_BEND_NAME=blake3 BLAKE3-bend/bend/rust/gen.sh vendor/blake3
```

```toml
[patch.crates-io]
blake3 = { path = "vendor/blake3" }
```

Building needs clang (the engine is the C that Bend2 emits); without it, the
crate builds as upstream's and says so in a warning. `BLAKE3_BEND=0` turns
the engine off at run time, `BLAKE3_BEND_THREADS=<n>` caps its threads,
`BLAKE3_BEND_TRACE=1` prints what it did.

How it works, and the benchmarks:
[github.com/gunta/BLAKE3-bend](https://github.com/gunta/BLAKE3-bend) (see
`bend/lib/README.md`).

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The bundled `csrc/engine.c` contains the Bend2 runtime, Apache-2.0.
