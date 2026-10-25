#!/bin/sh
# Regenerates the engine's C, the one file every drop-in package compiles
# (the Bend runtime, blake3.bend and engine.c, as Bend emits them, patched
# to embed): bend/lib/csrc/engine.c, and the copy in each package that
# ships it. Run it after any change to the .bend or engine sources, then
# commit the copies with them. Needs Bend2 (~/.bend/bin/bend).
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
for pkg in rust; do
  if [ -d "$root/bend/$pkg/csrc" ]; then
    cp "$out" "$root/bend/$pkg/csrc/engine.c"
  fi
done
echo "wrote $out ($(wc -c < "$out") bytes, $("$BEND" version))"
