#!/bin/sh
# Builds libblake3-bend into bend/lib/build (or $1):
#   include/blake3.h, include/blake3_bend.h   the official header, unchanged
#   lib/libblake3.a, lib/libblake3.{dylib,so} the official C library with
#                                             its subtree hook, plus the
#                                             Bend engine (engine.bend)
#   bin/blake3                                the test CLI (cli.c)
# Needs clang (Apple's, or LLVM 19+) and Bend2 (~/.bend/bin/bend).
# PORTABLE=1 builds for the baseline CPU instead of this one.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="${1:-$here/build}"
BEND="${BEND:-$HOME/.bend/bin/bend}"
CC="${CC:-clang}"
arch=$(uname -m)
src="$out/src"
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

# 1. the engine: Bend -> C, made fit to embed
python3 "$root/bend/tools/gen_blake3.py" >/dev/null
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
rm -f "$src/engine.c"
log=$("$BEND" "$here/engine.bend" -o "$src/engine.c" 2>&1) || true
[ -f "$src/engine.c" ] || { printf '%s\n' "$log" >&2; echo "bend failed for engine.bend" >&2; exit 1; }
if grep -q "define BANGS   [1-9]" "$src/engine.c"; then
  echo "engine.bend has a ! call: the library builds CPU-only C" >&2
  exit 1
fi
python3 "$here/patch.py" embed "$src/engine.c"

# 2. the official sources, with the hook
for f in blake3.c blake3.h blake3_impl.h blake3_dispatch.c blake3_portable.c blake3_neon.c \
         blake3_sse2_x86-64_unix.S blake3_sse41_x86-64_unix.S \
         blake3_avx2_x86-64_unix.S blake3_avx512_x86-64_unix.S; do
  cp "$root/c/$f" "$src/$f"
done
cp "$here/blake3_bend.c" "$here/blake3_bend.h" "$src/"
python3 "$here/patch.py" hook "$src/blake3.c"

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
