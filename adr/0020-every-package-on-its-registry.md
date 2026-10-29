# ADR 0020: Every package on its registry, prebuilt

Date: 2026-10-29
Status: accepted (the pipeline is in the repository; 1.8.8 is its first release)

## Context

Until 1.8.7 only the command line was published (crates.io, Homebrew,
GitHub Releases). The library crate was a git dependency, and the Python and
npm packages installed from the repository and compiled the engine on the
user's machine with clang, falling back to the official C (Python) or Bend's
JavaScript (npm) without it. The Go module had no tagged version. npm now
blocks install scripts by default unless allowed, and Bun runs none for
dependencies, so a package that builds on install is a package that
silently runs on its slow path.

The user asked for every binding on its own registry, with a native install
that is easy for everyone.

## Decision

One `turboblake-v<version>` tag publishes every package of that version
(`.github/workflows/turboblake-release.yml`), each prebuilt piece built for
the baseline CPU the command line already uses (Apple M1, x86-64-v3, armv8)
and tested before anything is published:

| registry | package | prebuilt for |
|---|---|---|
| crates.io | `turboblake` (library and command line) | source; clang tunes the engine for the machine |
| npm | `turboblake`, plus `@turboblake/<platform>` as optionalDependencies | darwin-arm64, darwin-x64, linux-x64-gnu, linux-arm64-gnu |
| PyPI | `turboblake` (module `blake3`), wheels and sdist | macOS arm64 and x86-64; manylinux_2_28 and musllinux_1_2, x86-64 and aarch64; CPython 3.9-3.14 |
| Go | tag `bend/go/v<version>` | the engine `.syso` objects already in the module |

- **npm** follows esbuild's layout: one small package per platform holding
  `turboblake.node` (`bend/node/prebuilt.mjs` writes it), with `os`, `cpu`
  and `libc` so package managers fetch only the matching one. The loader
  takes an addon built in place first (`TURBOBLAKE_BUILD=1 npm rebuild`
  builds one tuned for this CPU), then the platform package, then Bend's
  JavaScript. The install script skips the build when the platform package
  is there. Linux addons build in manylinux_2_28 and need glibc 2.17.
- **PyPI** wheels come from the sdist (cibuildwheel, settings in
  `bend/python/pyproject.toml`), so the sdist is known to build. The sdist
  now carries all of `csrc` (MANIFEST.in) and the license files.
- `TURBOBLAKE_TARGET_CPU`, which the crate already read, is read by the npm
  and Python builds too.
- crates.io and PyPI publish by trusted publishing from the `release`
  environment; npm by the `NPM_TOKEN` secret, with provenance.

## Checked

On an Apple M5 Pro and in Docker (linux/arm64): the darwin-arm64 platform
package installs beside `turboblake` from tarballs and runs native with npm's
install scripts blocked; the linux-arm64-gnu addon built in manylinux_2_28
passes `test/test.mjs` (2100 vector checks, 2165 against @noble/hashes,
hashFiles) and needs GLIBC_2.17; the macOS arm64 wheel passes the 29 tests
(Metal found); cibuildwheel's manylinux and musllinux aarch64 wheels, built
from the sdist with the engine, pass 28 (GPU test skipped); `cargo publish
--dry-run` passes. The x86-64 builds and the publish steps run first in CI.

## Consequences

- Windows has no prebuilt package. npm installs there run on Bend's
  JavaScript. pip would build the sdist without the engine or the official
  SIMD, which is slower than the `blake3` wheel, against ADR 0016.
- The x86-64 prebuilts need AVX2 (x86-64-v3), as the command line does.
  An older CPU should build from source (`TURBOBLAKE_BUILD=1`, or pip's
  `--no-binary turboblake`).
- After 1.8.8 is on crates.io, `blake3-bend` can be yanked (ADR 0018).
- The C library has no registry here; it stays `bend/lib/build.sh`.
- Accounts: the npm org `turboblake` and the `NPM_TOKEN` secret; trusted
  publishers on PyPI (project `turboblake`, pending) and crates.io for this
  workflow and the `release` environment.
