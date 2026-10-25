#!/bin/sh
# Rebuilds everything the Bend2 port is checked and raced against, after a
# change here or in upstream BLAKE3, and fails on the first mismatch:
#   1. the official b3sum and the Rust reference benches (this repo's crate)
#   2. bend/blake3.bend from its generator, the Bend binaries, the crate's C
#   3. correctness: the official test vectors on both Bend paths, b3sum
#      output byte-identical to the official one, sizes around 1 GiB
#      segments (sparse files), and bao outboards byte-identical to bao-tree
#   4. benchmarks (skip with --no-bench): the one-shot race and the daemon
#      race, written to bend/bench/results/
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
bench=1
[ "${1:-}" = "--no-bench" ] && bench=0
step() { printf '\n== %s\n' "$*"; }
scratch=$(mktemp -d "${TMPDIR:-/tmp}/b3bend.XXXXXX")
trap 'rm -rf "$scratch"' EXIT

step "official b3sum and Rust references"
(cd b3sum && RUSTFLAGS="-C target-cpu=native" cargo build --release --features neon --quiet)
(cd bend/bench/rust && RUSTFLAGS="-C target-cpu=native" cargo build --release --quiet)
(cd bend/bench/iroh && RUSTFLAGS="-C target-cpu=native" cargo build --release --quiet)
ref="$root/b3sum/target/release/b3sum"

step "Bend: generate, build"
python3 bend/tools/gen_blake3.py
for p in test/vectors.bend bench/mem.bend bench/daemon.bend bench/obao.bend; do
  bend/build.sh "bend/$p" >/dev/null
done
bend/build.sh bend/b3sum.bend bend/build/b3sum >/dev/null
bend/crate/gen.sh
(cd bend/crate && cargo build --release --quiet)

step "official test vectors (CPU and GPU-shape paths)"
bend/test/build/vectors | python3 bend/test/check.py

step "b3sum output byte-identical to the official b3sum"
python3 - "$scratch" <<'PY'
import os, sys
d = sys.argv[1]
for n in [0, 1, 63, 64, 65, 1023, 1024, 1025, 2048, 7169, 8192, 8193, 16384,
          16385, 32768, 32769, 65536, 100000, 1048576, 1048577, 3333333]:
    open(os.path.join(d, f"e{n}.bin"), "wb").write(os.urandom(n))
PY
set -- "$scratch"/e*.bin
"$ref" "$@" > "$scratch/want.txt"
for bin in bend/build/b3sum bend/crate/target/release/b3bend; do
  "$bin" "$@" > "$scratch/got.txt"
  cmp "$scratch/want.txt" "$scratch/got.txt"
  echo "$bin: $# files identical"
done
cat "$scratch/e3333333.bin" | bend/build/b3sum > "$scratch/got.txt"
cat "$scratch/e3333333.bin" | "$ref" | cmp - "$scratch/got.txt" && echo "stdin identical"

step "files around the 1 GiB segment boundaries"
python3 bend/test/big.py "$scratch/big"

step "bao outboards byte-identical to bao-tree (iroh-blobs)"
mkdir -p "$scratch/ob"
bend/bench/build/obao "$scratch/ob" "$@" >/dev/null
bend/bench/iroh/target/release/ob-check "$scratch/ob" "$@" | tail -1

if [ "$bench" = 1 ]; then
  step "benchmarks"
  python3 bend/bench/race.py 11 | tee bend/bench/results/race.md
  python3 bend/bench/daemon.py 7 | tee bend/bench/results/daemon.md
fi
step "refresh passed"
