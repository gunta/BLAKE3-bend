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
CFLAGS="${CFLAGS:--O3 -mcpu=native}"
"$BEND" "$src" -o "$out.c" 2>&1 | grep -v -e "rely on unsafe" -e "depend on @unsafe" -e "SOME PROOFS FAIL" || true
[ -f "$out.c" ] || { echo "bend failed for $src" >&2; exit 1; }
clang -DBEND_METAL=1 -x objective-c -fobjc-arc -fmodules -std=c11 $CFLAGS "$@" \
  "$out.c" -lpthread -lm -o "$out"
if grep -q "define BANGS   [1-9]" "$out.c"; then
  "$out" +RTS --gpu-build -RTS >/dev/null
fi
echo "built $out"
