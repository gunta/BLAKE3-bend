#!/bin/sh
# The GitHub release's notes for a version: how to install each package,
# and how to check that a file came from this repository's release build.
#   notes.sh VERSION
set -eu
v=$1
cat <<NOTES
turboblake $v: BLAKE3, turbocharged. The official b3sum, blake3 crate, C library and bindings, with big inputs and many files hashed on every core by a Bend2 engine.

| | install |
|---|---|
| command line | \`brew install gunta/tap/turboblake\` · \`cargo binstall turboblake\` · \`cargo install turboblake\` · or an archive below |
| Rust | \`cargo add turboblake\` (still \`use blake3\`) |
| Python | \`pip install turboblake\` (still \`import blake3\`) |
| Node, Bun, Deno | \`npm install turboblake\` |
| Go | \`go get github.com/gunta/turboblake/bend/go@v$v\` |
| C | \`brew install gunta/tap/libturboblake\`, or a \`libturboblake\` archive below (pkg-config and CMake files included) |

Prebuilt for macOS (arm64, x86-64), Linux (glibc 2.28+ and musl, arm64 and x86-64) and Windows (x86-64, arm64). The x86-64 builds take AVX2 when the CPU has it and run on any x86-64 CPU. On Windows the engine is not there yet: the packages are the official BLAKE3 code there, never slower than it.

Every file below is in \`SHA256SUMS\` and has a build provenance attestation from this release's workflow:

\`\`\`bash
gh attestation verify turboblake-$v-x86_64-unknown-linux-gnu.tar.gz --repo gunta/turboblake
\`\`\`

Benchmarks and method: https://gunta.github.io/turboblake/
NOTES
