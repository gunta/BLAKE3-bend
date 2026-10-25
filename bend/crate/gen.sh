#!/bin/sh
# Regenerates csrc/b3sum.c from bend/b3sum.bend with the local Bend2
# toolchain (~/.bend/bin/bend). Run it after any change to the .bend or
# effect sources, then commit csrc/b3sum.c with them.
set -e
here=$(cd "$(dirname "$0")" && pwd)
bend_dir="$here/.."
BEND="${BEND:-$HOME/.bend/bin/bend}"
python3 "$bend_dir/tools/gen_blake3.py" >/dev/null
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
out="$here/csrc/b3sum.c"
rm -f "$out"
"$BEND" "$bend_dir/b3sum.bend" -o "$out" >/dev/null 2>&1 || true
[ -s "$out" ] || { "$BEND" "$bend_dir/b3sum.bend" --check-only; exit 1; }
if grep -q "define BANGS   [1-9]" "$out"; then
  echo "b3sum.bend has a ! call: the crate builds CPU-only C" >&2
  exit 1
fi
echo "wrote $out ($(wc -c < "$out") bytes, $("$BEND" version))"
