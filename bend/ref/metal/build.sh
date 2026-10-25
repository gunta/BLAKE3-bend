#!/bin/sh
# Builds the native Metal reference: the kernel source (b3core.h + b3.metal)
# is embedded in the binary and compiled by the Metal driver at start-up, so
# no offline Metal toolchain is needed.
# usage: bend/ref/metal/build.sh [out]
set -e
here=$(cd "$(dirname "$0")" && pwd)
out="${1:-$here/build/b3metal}"
mkdir -p "$here/build"
cat "$here/../b3core.h" "$here/b3.metal" > "$here/build/b3_all.metal"
(cd "$here/build" && xxd -i b3_all.metal > b3_src.h)
clang -O2 -fobjc-arc -I"$here/build" "$here/b3metal.m" \
  -framework Metal -framework Foundation -o "$out"
echo "built $out"
