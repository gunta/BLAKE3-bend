#!/bin/sh
# The one command when anything upstream moves: BLAKE3, blake3-py, the Go
# and JS packages our bindings mirror, Bend2 (scripts/upstream/upstreams.json).
#   1. says what moved (scripts/upstream/upstream.py status), and stops if
#      nothing did
#   2. merges upstream BLAKE3 on a sync/upstream-YYYYMMDD branch cut from
#      master (scripts/sync-upstream.sh --merge --no-bench, which regenerates
#      and re-checks through scripts/refresh.sh), or just cuts the branch
#   3. three-way merges the files we copy from the other upstreams
#   4. writes the brief, .upstream/REPORT.md: every diff that matters
#   5. hands the branch and the brief to a coding agent (claude), which
#      decides what to adopt (scripts/upstream/AGENT.md), finishes the merge,
#      regenerates, verifies (scripts/upstream/verify.sh), pins, commits, and
#      writes .upstream/DECISIONS.md
# Nothing is pushed, released, or merged into master.
#
#   scripts/update-upstream.sh              all of it; the agent interactive
#   scripts/update-upstream.sh --headless   the agent on its own (claude -p)
#   scripts/update-upstream.sh --no-agent   stop after the brief
#   scripts/update-upstream.sh --force      go on when nothing moved
# AGENT="codex exec" (or any command taking the prompt as its last argument)
# runs another agent.
set -eu
cd "$(dirname "$0")/.."
agent=interactive force=0
for a in "$@"; do
  case $a in
    --headless) agent=headless;;
    --no-agent) agent=none;;
    --force) force=1;;
    *) echo "usage: $0 [--headless|--no-agent] [--force]" >&2; exit 2;;
  esac
done
[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo "commit or stash your changes first" >&2; exit 1; }
up="python3 scripts/upstream/upstream.py"
mkdir -p .upstream

moved=0
UPSTREAM_BASE=master $up status > .upstream/status.txt || moved=$?
cat .upstream/status.txt
[ "$moved" = 0 ] || [ "$moved" = 3 ] || exit "$moved"
if [ "$moved" = 0 ] && [ "$force" = 0 ]; then
  echo "everything is current"; exit 0
fi

branch="sync/upstream-$(date +%Y%m%d)"
: > .upstream/sync.log
if grep -q "^blake3 .* moved" .upstream/status.txt; then
  echo "merging upstream BLAKE3 and re-checking (log: .upstream/sync.log)"
  if scripts/sync-upstream.sh --merge --no-bench > .upstream/sync.log 2>&1; then
    echo "BLAKE3 merged, refresh passed"
  else
    tail -15 .upstream/sync.log
    echo "sync-upstream.sh stopped (conflicts or a failed check): the agent takes it from here"
  fi
else
  git checkout -q -B "$branch" master
  echo "BLAKE3 is current; on $branch"
fi

$up apply > .upstream/apply.log 2>&1 || true
cat .upstream/apply.log
$up report

prompt="Take this upstream update for turboblake. Follow scripts/upstream/AGENT.md; the report is .upstream/REPORT.md. You are on branch $(git branch --show-current)."
case $agent in
  none)
    cat <<MSG

Brief ready: .upstream/REPORT.md, on $(git branch --show-current).
Hand it to an agent with:  claude "$prompt"
MSG
    ;;
  headless)
    # edits and commands without asking, except anything that leaves this machine
    if [ -n "${AGENT:-}" ]; then $AGENT "$prompt"; else
      claude -p --permission-mode acceptEdits --allowedTools Bash \
        --disallowedTools "Bash(git push:*)" "Bash(git tag:*)" "Bash(gh:*)" \
          "Bash(cargo publish:*)" "Bash(npm publish:*)" "Bash(twine:*)" "Bash(bend update:*)" \
        -- "$prompt"
    fi
    ;;
  interactive)
    ${AGENT:-claude} "$prompt"
    ;;
esac
