#!/bin/sh
# Builds a Bend program the way `bend x.bend -o x` does, plus CPU tuning:
# bend emits one C file (host program + GPU kernel); clang builds the host,
# and the binary's --gpu-build writes the Metal archive (x.gpu) beside it.
# usage: bend/build.sh path/to/prog.bend [out] [extra clang flags...]
set -e
src="$1"; shift
out="${1:-$(dirname "$src")/build/$(basename "$src" .bend)}"; [ $# -gt 0 ] && shift
mkdir -p "$(dirname "$out")"
BEND="${BEND:-$HOME/.bend/bin/bend}"
# The SLP flags let clang pack compress8's eight lanes into NEON registers
# (ADR 0002): 8 x 64-bit result stores make a 512-bit seed, and the tree
# behind it is ~1700 instructions deep.
CFLAGS="${CFLAGS:--O3 -mcpu=native -mllvm -slp-max-reg-size=512 -mllvm -slp-recursion-max-depth=100000 -mllvm -slp-threshold=-20 -mllvm -inline-threshold=20000}"
# compress8 is one def of ~3600 lets: the checker (Bun/JSC) needs a deep stack.
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
rm -f "$out.c"
log=$("$BEND" "$src" -o "$out.c" 2>&1) || true
[ -f "$out.c" ] || { printf '%s\n' "$log" >&2; echo "bend failed for $src" >&2; exit 1; }
if grep -q "define BANGS   [1-9]" "$out.c"; then
  clang -DBEND_METAL=1 -x objective-c -fobjc-arc -fmodules -std=c11 $CFLAGS "$@" \
    "$out.c" -lpthread -lm -o "$out"
  "$out" +RTS --gpu-build -RTS >/dev/null
else
  # No ! call: a plain C build links only libSystem, so dyld does not load
  # Metal and Foundation at every start (2.7 ms -> 1.4 ms for b3sum).
  clang -x c -std=c11 $CFLAGS "$@" "$out.c" -lpthread -lm -o "$out"
fi
echo "built $out"
