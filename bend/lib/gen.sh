#!/bin/sh
# Regenerates bend/lib/csrc, the C every drop-in package compiles: the
# engine (the Bend runtime, blake3.bend and engine.c, as Bend emits them,
# patched to embed), the official C library with its hook, and the glue.
# Run it after any change to the .bend, engine or glue sources, then commit
# csrc with them. Needs Bend2 (~/.bend/bin/bend).
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
BEND="${BEND:-$HOME/.bend/bin/bend}"
out="$here/csrc/engine.c"
mkdir -p "$here/csrc"
python3 "$root/bend/tools/gen_blake3.py" >/dev/null
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
rm -f "$out"
log=$("$BEND" "$here/engine.bend" -o "$out" 2>&1) || true
[ -s "$out" ] || { printf '%s\n' "$log" >&2; echo "bend failed for engine.bend" >&2; exit 1; }
if grep -q "define BANGS   [1-9]" "$out"; then
  echo "engine.bend has a ! call: the engine is CPU-only C" >&2
  exit 1
fi
python3 "$here/patch.py" embed "$out"
# The rest of the C library, beside it: the official sources with the hook,
# and the glue. Every binding builds from this one directory.
for f in blake3.c blake3.h blake3_impl.h blake3_dispatch.c blake3_portable.c blake3_neon.c \
         blake3_sse2_x86-64_unix.S blake3_sse41_x86-64_unix.S \
         blake3_avx2_x86-64_unix.S blake3_avx512_x86-64_unix.S; do
  cp "$root/c/$f" "$here/csrc/$f"
done
cp "$here/blake3_bend.c" "$here/blake3_bend.h" "$here/csrc/"
python3 "$here/patch.py" hook "$here/csrc/blake3.c"
cp "$out" "$root/bend/rust/blake3-bend/csrc/engine.c" 2>/dev/null || true
echo "wrote $here/csrc ($(wc -c < "$out") bytes of engine, $("$BEND" version))"
