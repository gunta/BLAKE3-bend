#!/bin/sh
# The proof gate: checks every law of LAWS.bend against PROOF.bend and
# prints ALL PROOFS CHECK when they all hold (ADR 0007).
# usage: bend/prove.sh [--verdict]
set -e
cd "$(dirname "$0")"
BEND="${BEND:-$HOME/.bend/bin/bend}"
# compress8 is one def of ~3600 lets: the checker (Bun/JSC) needs a deep stack.
ulimit -s 65520 2>/dev/null || true
export BUN_JSC_maxPerThreadStackUsage=60000000 JSC_maxPerThreadStackUsage=60000000
exec "$BEND" PROOF.bend "$@"
