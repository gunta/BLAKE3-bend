#!/bin/sh
# Builds libturboblake for a target with CMake (bend/lib/CMakeLists.txt),
# static and shared, and writes libturboblake-<version>-<target>.tar.gz into
# OUT: include/turboblake/, lib/ (libturboblake.a and the shared library),
# lib/pkgconfig/libturboblake.pc and lib/cmake/turboblake/. Also leaves the
# test command line (cli.c) at OUT/blake3-<target>, for bend/lib/test.py.
#   build-lib.sh TARGET OUT
set -eu
. "$(dirname "$0")/common.sh"
target=$1
out=$(mkdir -p "$2" && cd "$2" && pwd)
name="libturboblake-$version-$target"
work=$(mktemp -d)
prefix="$work/$name"
cpu=$(engine_cpu "$target")
# a static library and the test CLI first; then the shared one, whose CMake
# export is the one installed
for shared in OFF ON; do
  cmake -S "$root/bend/lib" -B "$work/build-$shared" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="${CC:-clang}" -DBUILD_SHARED_LIBS=$shared -DTURBOBLAKE_CLI=ON \
    -DTURBOBLAKE_TARGET_CPU="${cpu:-baseline}" -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 >/dev/null
  cmake --build "$work/build-$shared" --parallel
  cmake --install "$work/build-$shared" --prefix "$prefix" >/dev/null
done
cp "$work/build-OFF/blake3" "$out/blake3-$target"
cp "$root/bend/lib/README.md" "$root/LICENSE_A2" "$root/LICENSE_A2LLVM" "$root/LICENSE_CC0" "$prefix/"
(cd "$work" && tar czf "$out/$name.tar.gz" "$name")
rm -rf "$work"
say "wrote $out/$name.tar.gz"
