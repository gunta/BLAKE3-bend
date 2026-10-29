# ADR 0020: Every package on its registry, prebuilt, on every CPU

Date: 2026-10-29
Status: accepted (the pipeline is in the repository; 1.8.8 is its first release)

## Context

Until 1.8.7 only the command line was published (crates.io, Homebrew,
GitHub Releases). The library crate was a git dependency; the Python and
npm packages installed from the repository and compiled the engine on the
user's machine with clang; the Go module had no tagged version; the C
library was `build.sh` in a clone. npm now blocks install scripts unless
allowed, and Bun runs none for dependencies, so a package that builds on
install silently runs on its slow path.

Four gaps stood behind "prebuilt": the x86-64 builds were compiled for
x86-64-v3 and died with an illegal instruction on a CPU without AVX2 (the
Go linux/arm64 object, built for Neoverse N1, likewise on an ARMv8.0 core);
nothing ran on Windows; nothing was built for musl; the release Linux
binaries were linked on Ubuntu 24.04 and needed its glibc 2.39.

The user asked for every binding on its own registry, an easy native
install for everyone, npm as the one package `turboblake` under their own
account, and a secure, repeatable release on CI.

## Decision

**The engine checks the CPU.** Each prebuilt engine is compiled for its
platform's baseline (x86-64-v3, Apple M1, armv8), and nothing compiled for
that baseline runs before `b3e_cpu_ok` (bend/lib/engine.c) has read cpuid
and found every feature the compiler assumed (`__AVX2__`, `__FMA__`,
`__BMI2__`, ... as the macros say; XCR0 for the vector state). The entry
points are compiled for plain x86-64 (`target("arch=x86-64")`), and the
runtime's constructors, which used to run at load, run from `b3e_boot`
after the check (patch.py `embed`). On an older CPU the engine never starts
and every input is hashed by the official C, which picks its own SIMD at
run time. Checked under qemu: the 1.8.7 engine dies on a Westmere and a
Core 2; this one hashes right on both, and runs the engine on a Haswell.
Only the engine gets CPU flags now (build.mjs gave them to the official C
too). `TURBOBLAKE_CPU=0` forces the old-CPU path.

**One release, every registry.** `bend/VERSION` is the version;
`scripts/release/version.py` writes and checks it in every manifest, and
`bend/rust/gen.sh` puts it in the crate. A `turboblake-v<version>` tag
runs `turboblake-release.yml`, which calls `turboblake-build.yml` (also
run on every pull request and on master) and publishes exactly what it
built and tested:

| registry | package | prebuilt for |
|---|---|---|
| GitHub release | `turboblake-<v>-<target>` (command line), `libturboblake-<v>-<target>` (C) | macOS arm64/x86-64; Linux gnu (glibc 2.28+) and musl (static), arm64/x86-64; Windows x86-64/arm64 (command line) |
| crates.io | `turboblake`, library and command line | source; `cargo binstall` takes the archives |
| npm | `turboblake`, one package, its addons in `prebuilds/` | darwin arm64/x64, linux gnu and musl arm64/x64, win32 x64/arm64 |
| PyPI | `turboblake` (module `blake3`) | macOS, manylinux_2_28, musllinux_1_2, arm64/x86-64, every CPython from 3.9; Windows (installs `blake3`) |
| Go proxy | tag `bend/go/v<version>` | the engine objects in the module (rebuilt, with the check) |
| Homebrew tap | `turboblake`, `libturboblake` | from the release archives |

- **npm** is one package, as the user asked (no scope, no organisation):
  it carries an addon for each of 8 platforms (about 3 MB unpacked) and
  `index.js` loads the one for this machine, glibc or musl told apart by
  `process.report`. There is no install script, so nothing is blocked and
  nothing runs at install. A platform without an addon runs on Bend's
  JavaScript; `node build.mjs` in the package builds one.
- **Windows.** The engine is POSIX C (threads, an 8 TiB `mmap` window,
  signals); porting the Bend runtime is its own project. Until then every
  Windows build is the official BLAKE3 code and nothing else, so it is
  never slower than upstream (ADR 0016): the command line and crate are
  upstream's b3sum and blake3 (build.rs skips the engine off Unix); the npm
  addon is the official C with its Windows assembly, and finds Node-API in
  the host process (`src/napi_win.h`) so it loads in Node, Bun, Deno and
  Electron alike; the Go package compiles the official C with MinGW; and
  turboblake's wheel on Windows holds no module and depends on `blake3`.
  The same holds wherever the Python sdist finds no clang.
- **Linux** builds run in manylinux_2_28 (glibc 2.28: RHEL 8, Debian 10,
  Ubuntu 20.04) and Alpine containers; `build-npm.sh` fails an addon that
  asks for a newer glibc.
- **The C library** gets a CMake build (`bend/lib/CMakeLists.txt`) that
  installs `include/turboblake/blake3.h`, `libturboblake` (static and
  shared), `libturboblake.pc` and a `turboblake::turboblake` CMake package:
  what Homebrew, distributions and vcpkg-style ports consume. The headers
  sit under `turboblake/` so they never shadow an installed official
  `blake3.h`.
- **Homebrew.** The release renders both tap formulas from SHA256SUMS
  (`scripts/release/formulas.py`), installs and tests them with brew on
  macOS, then pushes them to gunta/homebrew-tap. It also opens a pull
  request with the homebrew-core draft's new crate checksum.

**Securing it.**
- crates.io, PyPI and npm publish by trusted publishing (OIDC): no
  long-lived registry token in the repository. npm's first publish needs a
  token once, before npm can know the trusted publisher.
- Publishing jobs run in the `release` environment, which can require a
  reviewer's approval for each release.
- Every action is pinned to a commit SHA (Dependabot keeps the pins
  current); every job starts from `permissions: {}` and asks for what it
  uses; checkouts keep no credentials unless the job pushes; no workflow
  expression is spliced into a shell script; zizmor and actionlint check
  the workflows on every change (`workflows-lint.yml`).
- The release binaries build `--locked` against the crate's committed
  Cargo.lock.
- Every released file is in SHA256SUMS and has a build provenance
  attestation (`gh attestation verify FILE --repo gunta/turboblake`); npm
  packages carry npm provenance; PyPI files carry attestations from trusted
  publishing.
- Each publish step is skipped when its version is already there, so a
  failed release is re-run, not repaired by hand. The GitHub release stays
  a draft until crates.io, npm and PyPI all have the version.
- `scripts/release/prepare.sh X.Y.Z` (set the version, regenerate, check,
  commit) and `scripts/release/tag.sh` (tag only a clean origin/master whose
  turboblake-build passed, signed when git has a key, pushed after a
  prompt) are the two commands a release takes.

## Checked

On an Apple M5 Pro and in Docker (linux/arm64, and linux/amd64 under
Rosetta): libturboblake's 5,270 checks through build.sh and through CMake;
the engine's CPU check under qemu (above); the CMake package and
pkg-config file linked by a program; Go's tests on darwin/arm64,
linux/arm64 and linux/amd64 with the rebuilt objects, and a cross-compile
for windows/amd64 and arm64; the Windows npm addon cross-compiled and
linked for x64 and arm64 with no Node-API import library; the npm package
packed with prebuilds and installed into an empty project, native under
Node and Bun with npm's install scripts blocked; the manylinux and
musllinux aarch64 wheels from the sdist (tests pass), the macOS wheel, and
the no-clang sdist build that installs `blake3`; the Linux release builds
in their containers; `cargo publish --dry-run`. The x86-64 macOS, Windows
and publishing steps run first in CI.

## Consequences

- Windows has no engine: it is as fast as the official BLAKE3, not faster.
- An x86-64 CPU without AVX2 runs the official C rather than the engine:
  correct, on the official SIMD, without the engine's cores. Building from
  source (`cargo install`, `node build.mjs`, pip's `--no-binary
  turboblake`) tunes the engine for that CPU instead.
- After 1.8.8 is on crates.io, `blake3-bend` can be yanked (ADR 0018).
- Accounts, once: npm (publish under the user's account; `NPM_TOKEN` for the
  first release, then a trusted publisher), PyPI and crates.io trusted
  publishers for `turboblake-release.yml` and the `release` environment, and
  a `HOMEBREW_TAP_TOKEN` for the tap.
