#!/bin/sh
# Refreshes the Go module's C from bend/lib/csrc, and the prebuilt engine
# for this machine's platforms: engine_<os>_<arch>.syso, the engine compiled
# with clang and the vectorizer flags cgo will not pass (-mllvm), for a
# baseline CPU of each platform. A platform with no .syso compiles the
# engine through cgo instead (c_engine.c), at plain flags: slower, still on
# every core. The Linux objects come from bend/bench/modal_linux.py (steps
# go). Commit the result.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
[ -s "$root/bend/lib/csrc/engine.c" ] || "$root/bend/lib/gen.sh"
rm -rf "$here/csrc"
cp -R "$root/bend/lib/csrc" "$here/csrc"
SLP="-mllvm -slp-max-reg-size=512 -mllvm -slp-recursion-max-depth=100000 -mllvm -slp-threshold=-20 -mllvm -inline-threshold=20000"
engine() {  # <goos_goarch> <clang target flags...>
  out="$here/engine_$1.syso"; shift
  clang -x c -std=c11 -O3 "$@" $SLP -fPIC -w -DBEND_EMBED -Dmain=b3e_bend_main \
    -c "$here/csrc/engine.c" -o "$out"
  echo "built $out"
}
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    engine darwin_arm64 -target arm64-apple-macos11 -mcpu=apple-m1
    engine darwin_amd64 -target x86_64-apple-macos11 -march=x86-64-v3
    ;;
  Linux-x86_64)
    engine linux_amd64 -march=x86-64-v3
    ;;
  Linux-aarch64)
    engine linux_arm64 -mcpu=neoverse-n1
    ;;
esac
# c_engine.c builds the engine through cgo only where no .syso is checked in
cons=""
for f in "$here"/engine_*.syso; do
  [ -e "$f" ] || continue
  p=$(basename "$f" .syso); p=${p#engine_}
  cons="$cons && !(${p%_*} && ${p#*_})"
done
cat > "$here/c_engine.c" <<C
//go:build cgo${cons}

// The engine for a platform with no prebuilt engine_<os>_<arch>.syso:
// compiled by cgo, which will not pass the vectorizer's -mllvm flags, so
// its 8-lane compression runs scalar. Slower; still on every core.
#define BEND_EMBED 1
#define main b3e_bend_main
#include "csrc/engine.c"
C
echo "wrote $here/c_engine.c (${cons:- every platform})"
