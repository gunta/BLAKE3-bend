#!/bin/sh
# Regenerates everything made from upstream code and checks every package,
# after taking an upstream change (scripts/update-upstream.sh, AGENT.md).
# scripts/refresh.sh covers the official b3sum, the Bend port, bend/lib's C,
# the crate and the CLI; this adds what it leaves out:
#   1. scripts/refresh.sh --no-bench (bend/lib/gen.sh, bend/rust/gen.sh, ...)
#   2. the proofs (bend/prove.sh)
#   3. libturboblake against the vectors and b3sum (bend/lib/test.py)
#   4. the crate: upstream's Rust tests and the CLI tests, with the engine
#   5. Go: bend/go/gen.sh (DOCKER=1 also builds the Linux .syso), go test
#   6. Python: blake3-py's tests on a fresh build of bend/python
#   7. Node: the addon and the bend-js build, npm test
# then lists the generated files that changed, to commit with the change.
# A missing go or node skips its step, and says so; anything else that fails
# stops here.
#   scripts/upstream/verify.sh [--bench]   --bench: refresh.sh's races too
set -eu
cd "$(dirname "$0")/../.."
root=$(pwd)
bench=--no-bench
[ "${1:-}" = "--bench" ] && bench=
step() { printf '\n== %s\n' "$*"; }
skipped=""

step "refresh (b3sum, the Bend port, bend/lib, the crate)"
scripts/refresh.sh $bench

step "proofs"
bend/prove.sh | tail -1 | tee /dev/stderr | grep -q "ALL PROOFS CHECK"

step "libturboblake"
bend/lib/build.sh >/dev/null
B3SUM="$root/b3sum/target/release/b3sum" python3 bend/lib/test.py

step "the turboblake crate's tests (upstream's, and b3sum's)"
log="$root/.upstream/crate-test.log"
mkdir -p "$root/.upstream"
if (cd bend/crate && cargo test --release --quiet >"$log" 2>&1); then
  grep "^test result" "$log"
else
  tail -40 "$log"; echo "crate tests failed: $log" >&2; exit 1
fi

if command -v go >/dev/null 2>&1; then
  step "Go"
  bend/go/gen.sh
  (cd bend/go && go test -count=1 ./...)
else
  skipped="$skipped go"
fi

step "Python"
venv="$root/.upstream/venv"
[ -x "$venv/bin/python" ] || python3 -m venv "$venv"
"$venv/bin/pip" install -q --upgrade pip pytest numpy
"$venv/bin/pip" install -q --force-reinstall --no-deps ./bend/python
# from outside bend/python, so `import blake3` is the installed build
(cd "$root/.upstream" && "$venv/bin/python" -m pytest "$root/bend/python/tests" -q)

if command -v node >/dev/null 2>&1; then
  step "Node"
  (cd bend/node && npm ci --silent && npm run build && npm test)
else
  skipped="$skipped node"
fi

step "generated files that changed (commit them with the change)"
git status --short -- bend/crate bend/lib/csrc bend/go bend/node/js bend/blake3.bend || true
[ -z "$skipped" ] || echo "skipped (not installed):$skipped"
step "verify passed"
