#!/bin/sh
# Emits bend/node/js/blake3.mjs: blake3.bend (here) to JavaScript, over the
# scalar half of the BLAKE3 code (gen_blake3.py --scalar > b3scalar.bend).
# turboblake's npm package runs it where its native addon cannot: browsers,
# workers, or a Node with no clang to build the addon. Commit the result.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
BEND="${BEND:-$HOME/.bend/bin/bend}"
python3 "$root/bend/tools/gen_blake3.py" --scalar "$here/b3scalar.bend"
out="$root/bend/node/js/blake3.mjs"
"$BEND" "$here/blake3.bend" -o "$out"
echo "wrote $out ($(wc -c < "$out") bytes)"
