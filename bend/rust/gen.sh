#!/bin/sh
# Generates the blake3-bend crate from this repository's copy of the
# official blake3 crate (Cargo.toml, build.rs, src/, c/, reference_impl/):
# the same API and tests, plus bend.rs, the engine's C, and the hook
# (patch_crate.py); and turboblake, the CLI, from the official b3sum
# (patch_b3sum.py, fast.rs). Writes bend/rust/blake3-bend and bend/crate
# (or only the library crate, to $1). Commit the result.
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
printf 'target/\nCargo.lock\n' > "$out/.gitignore"
python3 "$here/patch_crate.py" "$out" "$name"
echo "wrote $out ($name $(sed -n 's/^version = "\(.*\)"/\1/p' "$out/Cargo.toml" | head -1))"

# turboblake: the official b3sum on blake3-bend, with the fast path (fast.rs)
[ -n "$1" ] && exit 0
cli="$root/bend/crate"
rm -rf "$cli"
mkdir -p "$cli/src" "$cli/tests"
cp "$root/b3sum/Cargo.toml" "$root/b3sum/LICENSE_A2" "$root/b3sum/LICENSE_A2LLVM" "$root/b3sum/LICENSE_CC0" \
  "$root/b3sum/what_does_check_do.md" "$cli/"
cp "$root"/b3sum/src/*.rs "$cli/src/"
cp "$root"/b3sum/tests/*.rs "$cli/tests/"
cp "$here/fast.rs" "$cli/src/fast.rs"
printf '%s\n' "// turboblake installed as b3sum (cargo install turboblake --features replace)." \
  'include!("main.rs");' > "$cli/src/replace.rs"
cp "$here/README.turboblake.md" "$cli/README.md"
printf 'target/\nCargo.lock\n' > "$cli/.gitignore"
python3 "$here/patch_b3sum.py" "$cli"
echo "wrote $cli (turboblake $(sed -n 's/^version = "\(.*\)"/\1/p' "$cli/Cargo.toml" | head -1))"
