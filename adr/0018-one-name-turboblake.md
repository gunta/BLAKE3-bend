# ADR 0018: One name, turboblake

Date: 2026-10-26
Status: accepted (in the repository; the library ships under the name with the next crates.io release)

## Context

The product is turboblake: the command line (`cargo install turboblake`,
`brew install gunta/tap/turboblake`) and the Python and npm packages carry
the name. Underneath, the library kept the project's working name:

- the Rust library was a second crate, `blake3-bend` (1.8.7 on crates.io,
  no downloads), and the CLI crate depended on it;
- the C library was "libblake3-bend", with `blake3_bend.h`, `blake3_bend.c`,
  `blake3_bend_subtree` / `blake3_bend_running` and `-DBLAKE3_BEND`;
- the engine read `BLAKE3_BEND`, `BLAKE3_BEND_MIN`, `BLAKE3_BEND_THREADS`
  and `BLAKE3_BEND_TRACE`; builds read `BLAKE3_BEND_TARGET_CPU`,
  `BLAKE3_BEND_PORTABLE`, `BLAKE3_BEND_NO_ENGINE` and `BLAKE3_BEND_NAME`.

The user asked for one name everywhere: turboblake, not blake3-bend.

## Decision

**One crate.** `turboblake` is the library and the command line together,
generated into `bend/crate` by `bend/rust/gen.sh`: the library from the
official crate (`patch_crate.py`), then the official b3sum beside it
(`patch_b3sum.py`). The library keeps the name `blake3`, so
`turboblake = "1.8"` needs no other change in code (`use blake3::…`). The
binaries need a `cli` feature, on by default, so `cargo install turboblake`
works as before; it carries the command line's dependencies (anyhow, clap,
hex, wild) and the library's `mmap` and `rayon`. A library user who wants
none of them writes
`turboblake = { version = "1.8", default-features = false, features = ["std"] }`.
`bend/rust/blake3-bend` is gone; `TURBOBLAKE_NAME=blake3 bend/rust/gen.sh DIR`
still writes the library alone as a package named `blake3`, for `[patch]`.

The other way, a library crate `turboblake` and a CLI crate
`turboblake-cli`, was turned down: it would change `cargo install
turboblake`, the binstall metadata and every install line already out.

**C.** The library is libturboblake: `turboblake.h`, `turboblake.c`,
`turboblake_subtree`, `turboblake_running`, `-DTURBOBLAKE`. `build.sh`
still builds `libblake3.{a,dylib,so}`, the drop-in for the official
library, and adds `libturboblake.*` links to them, so `-lturboblake` and
`-lblake3` link the same library.

**Environment.** `TURBOBLAKE=0`, `TURBOBLAKE_MIN`, `TURBOBLAKE_THREADS`,
`TURBOBLAKE_TRACE`, `TURBOBLAKE_TARGET_CPU`, `TURBOBLAKE_PORTABLE`,
`TURBOBLAKE_NO_ENGINE`, `TURBOBLAKE_NAME`. The old names are not read: the
library is a day old and nothing outside this repository sets them. The
trace lines start with `turboblake:`.

**Kept.** The repository is `BLAKE3-bend` (site/BRAND.md), so its URLs,
the Go module path `github.com/gunta/BLAKE3-bend/bend/go` and the Pages URL
keep it. The engine's own symbols (`b3e_*`) are internal and unchanged.
ADRs through 0014 keep the names they were written with; 0015 and 0016,
which landed just before this rename, use the new ones.

## Verification

The rename was made on top of ADR 0014 (files past 4 TiB), ADR 0015
(proofs for every input) and ADR 0016 (never slower than b3sum). The C
that `bend/lib/gen.sh` regenerates, and the crate's library, build script
and command line that `bend/rust/gen.sh` regenerates, match the code
before the rename line for line once the old names are mapped to the new,
apart from two reworded comments. On an Apple
M5 Pro, with the engine taking every subtree
(`TURBOBLAKE_MIN=2048`): the crate's library tests (48), the CLI's unit and
integration tests (3 and 17) and the doc tests (15) pass; libturboblake's
1,495 checks (1,440 official vectors) pass, and a C program links with
`-lturboblake`; the Python module's 28 tests, the Node addon's tests (Node
and Bun) and the Go tests pass. A crate depending on `turboblake = { path }`
calls `blake3::hash`; with `default-features = false, features = ["std"]`
it pulls in none of clap, anyhow, hex or wild. The Go module's engine
objects were rebuilt (macOS here, Linux on Modal by
`bench/modal_linux.py --steps go`), so every platform reads the new names.
On Linux (Modal, x86-64 under gVisor) libturboblake's 1,525 checks, the
Python, Node, Bun and Go tests pass, and so do the crate's library tests
through the engine but upstream's `test_unmappable_linux`, which fails
there for upstream's own crate too.

## Consequences

- crates.io: `turboblake` 1.8.7 is the CLI alone, so the merged crate needs
  a new version to publish (the version is the user's call; upstream is
  still 1.8.7). After it ships, `blake3-bend` 1.8.7 can be yanked. Until
  then the READMEs give library users the git dependency
  (`turboblake = { git = "https://github.com/gunta/turboblake" }`), which
  cargo finds in `bend/crate`.
- The site's install page and library snippet change to `turboblake = "1.8"`
  when that release is out.

## Addendum: the repository too (2026-10-29)

The user asked for the repository's name to follow: `gunta/BLAKE3-bend` is
now `gunta/turboblake`. With it the Go module path is
`github.com/gunta/turboblake/bend/go` (and `/zeebo`), the site is
`gunta.github.io/turboblake/` (Astro `base: '/turboblake'`), and every
package's repository and homepage fields, install line and clone path say
turboblake. GitHub redirects the old repository URLs, git remotes and
`go get` of the old path, but not the old Pages URL. The "Kept" paragraph
above is history; only the internal `b3e_*` symbols keep their names.
