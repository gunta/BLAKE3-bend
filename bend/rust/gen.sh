#!/bin/sh
# Generates the blake3-bend crate from this repository's copy of the
# official blake3 crate (Cargo.toml, build.rs, src/, c/, reference_impl/):
# the same API and tests, plus bend.rs, the engine's C, and the hook
# (patch_crate.py). Writes bend/rust/blake3-bend, or $1. Commit the result.
#
# A package named "blake3", to [patch] a whole dependency graph:
#   BLAKE3_BEND_NAME=blake3 bend/rust/gen.sh vendor/blake3
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="${1:-$here/blake3-bend}"
name="${BLAKE3_BEND_NAME:-blake3-bend}"
[ -s "$root/bend/lib/csrc/engine.c" ] || "$root/bend/lib/gen.sh"
rm -rf "$out"
mkdir -p "$out/src" "$out/c" "$out/csrc" "$out/reference_impl"
cp "$root/Cargo.toml" "$root/build.rs" "$root/LICENSE_A2" "$root/LICENSE_A2LLVM" "$root/LICENSE_CC0" "$out/"
cp "$root"/src/*.rs "$out/src/"
cp "$here/bend.rs" "$out/src/bend.rs"
for f in "$root"/c/blake3*.c "$root"/c/blake3*.h "$root"/c/blake3*.S "$root"/c/blake3*.asm; do
  cp "$f" "$out/c/"
done
rm -f "$out/c/blake3_tbb.cpp"
cp "$root"/reference_impl/Cargo.toml "$root"/reference_impl/reference_impl.rs "$out/reference_impl/"
cp "$root/bend/lib/csrc/engine.c" "$out/csrc/engine.c"
cp "$here/README.md" "$out/README.md"
python3 "$here/patch_crate.py" "$out" "$name"
echo "wrote $out ($name $(sed -n 's/^version = "\(.*\)"/\1/p' "$out/Cargo.toml" | head -1))"
