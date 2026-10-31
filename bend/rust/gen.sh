#!/bin/sh
# Generates turboblake, one crate, into bend/crate: the library from this
# repository's copy of the official blake3 crate (Cargo.toml, build.rs, src/,
# c/, reference_impl/), with the same API and tests plus bend.rs, the
# engine's C and the hook (patch_crate.py); and on top of it the command
# line, the official b3sum with the fast path (patch_b3sum.py, fast.rs).
# `cargo add turboblake` is the library (still `use blake3`), `cargo install
# turboblake` the command. Commit the result.
#
# The library alone, as a package named "blake3", to [patch] a whole
# dependency graph:
#   TURBOBLAKE_NAME=blake3 bend/rust/gen.sh vendor/blake3
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="${1:-$root/bend/crate}"
name="${TURBOBLAKE_NAME:-turboblake}"
[ -s "$root/bend/lib/csrc/engine.c" ] || "$root/bend/lib/gen.sh"
lock=$(cat "$out/Cargo.lock" 2>/dev/null || true)
rm -rf "$out"
mkdir -p "$out/src" "$out/c" "$out/csrc" "$out/reference_impl"
cp "$root/Cargo.toml" "$root/build.rs" "$root/LICENSE_A2" "$root/LICENSE_A2LLVM" "$root/LICENSE_CC0" "$out/"
cp "$root"/src/*.rs "$out/src/"
cp "$here/bend.rs" "$out/src/bend.rs"
cp "$here/gpu.rs" "$out/src/gpu.rs"
for f in "$root"/c/blake3*.c "$root"/c/blake3*.h "$root"/c/blake3*.S "$root"/c/blake3*.asm; do
  cp "$f" "$out/c/"
done
rm -f "$out/c/blake3_tbb.cpp"
cp "$root"/reference_impl/Cargo.toml "$root"/reference_impl/reference_impl.rs "$out/reference_impl/"
cp "$root/bend/lib/csrc/engine.c" "$out/csrc/engine.c"
for f in turboblake_gpu.c turboblake_gpu.h turboblake_kernels.h b3core.h; do
  cp "$root/bend/lib/csrc/$f" "$out/csrc/$f"
done
cp "$here/README.md" "$out/README.md"
# Cargo.lock is kept (through the rm above): the release binaries build
# --locked, and `cargo install --locked` takes the same dependencies
printf 'target/\n' > "$out/.gitignore"
[ -n "$lock" ] && printf '%s\n' "$lock" > "$out/Cargo.lock"
python3 "$here/patch_crate.py" "$out" "$name"
version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$out/Cargo.toml" | head -1)

# the library alone ($1): done
if [ -n "$1" ]; then
  echo "wrote $out ($name $version, the library)"
  exit 0
fi

# the command line beside it: the official b3sum, with the fast path (fast.rs)
mkdir -p "$out/tests"
cp "$root/b3sum/what_does_check_do.md" "$out/"
cp "$root"/b3sum/src/*.rs "$out/src/"
cp "$root"/b3sum/tests/*.rs "$out/tests/"
cp "$here/recursive_tests.rs" "$out/tests/"
cp "$here/fast.rs" "$out/src/fast.rs"
printf '%s\n' "// turboblake installed as b3sum (cargo install turboblake --features replace)." \
  'include!("main.rs");' > "$out/src/replace.rs"
cp "$here/README.turboblake.md" "$out/README.md"
python3 "$here/patch_b3sum.py" "$out"
echo "wrote $out ($name $version, the library and the command line)"
