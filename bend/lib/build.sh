#!/bin/sh
# Builds libblake3-bend into bend/lib/build (or $1):
#   include/blake3.h, include/blake3_bend.h   the official header, unchanged
#   lib/libblake3.a, lib/libblake3.{dylib,so} the official C library with
#                                             its subtree hook, plus the
#                                             Bend engine (engine.bend)
#   bin/blake3                                the test CLI (cli.c)
# Needs clang (Apple's, or LLVM 19+); Bend2 (~/.bend/bin/bend) only to
# regenerate csrc/engine.c (gen.sh).
# PORTABLE=1 builds for the baseline CPU instead of this one.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="${1:-$here/build}"
CC="${CC:-clang}"
arch=$(uname -m)
src="$out/src"
BEND="${BEND:-$HOME/.bend/bin/bend}"
mkdir -p "$src" "$out/include" "$out/lib" "$out/bin"

if [ -n "$PORTABLE" ]; then
  cpu=""
elif [ "$arch" = x86_64 ]; then
  cpu="-march=native"
else
  cpu="-mcpu=native"
fi
# the engine's flags are bend/build.sh's (ADR 0002)
TUNE="-O3 $cpu -mllvm -slp-max-reg-size=512 -mllvm -slp-recursion-max-depth=100000 -mllvm -slp-threshold=-20 -mllvm -inline-threshold=20000"

# 1. the C (gen.sh makes csrc from engine.bend and c/; REGEN=1 remakes it)
stale=""
for f in "$here/engine.bend" "$here/engine.c" "$here/blake3_bend.c" "$here/blake3_bend.h" \
         "$here/patch.py" "$root/bend/hash.bend" "$root/bend/b3io.bend" "$root/bend/effs/load.c" \
         "$root/bend/effs/emit.c" "$root/bend/tools/gen_blake3.py"; do
  [ "$f" -nt "$here/csrc/engine.c" ] && stale=1
done
if [ -n "$REGEN" ] || [ -n "$stale" ] || [ ! -s "$here/csrc/engine.c" ]; then
  if [ -x "$BEND" ] || command -v bend >/dev/null; then
    "$here/gen.sh"
  else
    echo "note: csrc is older than its sources, and there is no Bend2 to remake it" >&2
  fi
fi
cp "$here"/csrc/* "$src/"

# 3. objects
C="-O3 -std=c11 -fPIC -fvisibility=default -DBLAKE3_BEND -I$src"
objs=""
cd "$src"
"$CC" -x c -std=c11 $TUNE -fPIC -w -DBEND_EMBED -Dmain=b3e_bend_main -c engine.c -o engine.o
objs="engine.o"
for f in blake3.c blake3_dispatch.c blake3_portable.c blake3_bend.c; do
  "$CC" $C $cpu -c "$f" -o "${f%.c}.o"
  objs="$objs ${f%.c}.o"
done
case "$arch" in
  arm64|aarch64)
    "$CC" $C $cpu -DBLAKE3_USE_NEON=1 -c blake3_neon.c -o blake3_neon.o
    objs="$objs blake3_neon.o"
    # dispatch must know NEON is linked in
    "$CC" $C $cpu -DBLAKE3_USE_NEON=1 -c blake3_dispatch.c -o blake3_dispatch.o
    ;;
  x86_64)
    for s in sse2 sse41 avx2 avx512; do
      "$CC" -c "blake3_${s}_x86-64_unix.S" -o "blake3_$s.o"
      objs="$objs blake3_$s.o"
    done
    ;;
  *)
    "$CC" $C -DBLAKE3_NO_SSE2 -DBLAKE3_NO_SSE41 -DBLAKE3_NO_AVX2 -DBLAKE3_NO_AVX512 \
      -c blake3_dispatch.c -o blake3_dispatch.o
    ;;
esac

# 4. libraries, header, test CLI
rm -f "$out/lib/libblake3.a"
ar rcs "$out/lib/libblake3.a" $objs
if [ "$(uname -s)" = Darwin ]; then
  "$CC" -dynamiclib -install_name @rpath/libblake3.0.dylib -o "$out/lib/libblake3.0.dylib" $objs -lpthread -lm
  ln -sf libblake3.0.dylib "$out/lib/libblake3.dylib"
else
  "$CC" -shared -Wl,-soname,libblake3.so.0 -o "$out/lib/libblake3.so.0" $objs -lpthread -lm
  ln -sf libblake3.so.0 "$out/lib/libblake3.so"
fi
cp "$src/blake3.h" "$here/blake3_bend.h" "$out/include/"
"$CC" -O2 -I"$out/include" "$here/cli.c" "$out/lib/libblake3.a" -lpthread -lm -o "$out/bin/blake3"
echo "built $out (libblake3.a, $(ls "$out/lib" | grep -v '\.a$' | head -1), bin/blake3)"
