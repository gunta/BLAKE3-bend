#!/bin/sh
# Builds the turboblake command for a target, checks it against the official
# test vectors, and writes its release archive into OUT:
# turboblake-<version>-<target>.tar.gz (.zip on Windows), the binary, README
# and licenses. Runs where the target's toolchain is (CI: macOS and Windows
# runners, Linux containers from setup-linux.sh).
#   build-cli.sh TARGET OUT
# The command stays on the CPU: no GPU backend (ADR 0006, 0013).
set -eu
. "$(dirname "$0")/common.sh"
target=$1
out=$(mkdir -p "$2" && cd "$2" && pwd)
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
rustup target add "$target" >/dev/null 2>&1 || true

export TURBOBLAKE_TARGET_CPU="$(engine_cpu "$target")" TURBOBLAKE_NO_GPU=1
case "$target" in
  *-linux-musl)
    # the engine and upstream's C with the system clang; a static binary
    export CC=clang "CC_$(echo "$target" | tr - _)=clang"
    ;;
esac
cd "$root/bend/crate"
cargo build --release --locked --target "$target"
bin="$root/bend/crate/target/$target/release/$(exe "$target")"

"${PYTHON:-python3}" "$root/bend/rust/check_vectors.py" "$bin"
"$bin" --version

name="turboblake-$version-$target"
stage=$(mktemp -d)
mkdir "$stage/$name"
cp "$bin" README.md LICENSE_A2 LICENSE_A2LLVM LICENSE_CC0 "$stage/$name/"
cd "$stage"
case "$target" in
  *-windows-*)
    if command -v 7z >/dev/null; then
      7z a -tzip -bso0 "$out/$name.zip" "$name"
    else
      powershell -NoProfile -Command "Compress-Archive -Path '$name' -DestinationPath '$(cygpath -w "$out/$name.zip")'"
    fi
    say "wrote $out/$name.zip"
    ;;
  *) tar czf "$out/$name.tar.gz" "$name" ; say "wrote $out/$name.tar.gz" ;;
esac
rm -rf "$stage"
