#!/bin/sh
# Builds a Bend program whose GPU runs 2^L groups of 128 lanes instead of the
# Metal default 2^7 (16384 lanes): bend -> C, then the C patched so CUBE (the
# per-lane memory: stacks, rings) and CUBE_LOG (the groups a bang runs) are
# both 128 << L, then build.sh's clang flags. An experiment on Bend 2.0.39's
# runtime (ADR 0006); run the result with a GPU heap big enough for the
# stacks, e.g. +RTS --gpu 4GB -RTS at L = 9.
# usage: bend/ref/bend/cube.sh prog.bend L out
set -e
src="$1"; lg="$2"; out="$3"
[ -n "$out" ] || { echo "usage: cube.sh prog.bend L out" >&2; exit 2; }
BEND="${BEND:-$HOME/.bend/bin/bend}"
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
mkdir -p "$(dirname "$out")"
rm -f "$out.orig.c"
"$BEND" "$src" -o "$out.orig.c" >/dev/null 2>&1 || true
[ -f "$out.orig.c" ] || { echo "bend failed for $src" >&2; exit 1; }
sed -e "s/^#define CUBE      ((u64)CUBE_T \* CUBE_T)/#define CUBE      ((u64)CUBE_T << $lg)/" \
    -e "s/^static u32    CUBE_LOG = 7;/static u32    CUBE_LOG = $lg;/" "$out.orig.c" > "$out.c"
grep -q "CUBE_T << $lg)" "$out.c" && grep -q "CUBE_LOG = $lg;" "$out.c" ||
  { echo "the runtime's cube lines changed; patch by hand" >&2; exit 1; }
clang -DBEND_METAL=1 -x objective-c -fobjc-arc -fmodules -std=c11 -O3 -mcpu=native \
  -mllvm -slp-max-reg-size=512 -mllvm -slp-recursion-max-depth=100000 \
  -mllvm -slp-threshold=-20 -mllvm -inline-threshold=20000 \
  "$out.c" -lpthread -lm -o "$out"
"$out" +RTS --gpu-build -RTS >/dev/null
echo "built $out (2^$lg groups of 128 lanes)"
