#!/bin/sh
# Brings the official BLAKE3 (BLAKE3-team/BLAKE3) into this fork, then
# re-checks and re-benchmarks the Bend2 port against it.
#
#   scripts/sync-upstream.sh            rebase our commits onto upstream/master
#   scripts/sync-upstream.sh --merge    merge upstream/master instead
#   scripts/sync-upstream.sh --no-bench skip the benchmarks at the end
#
# It works on a branch, sync/upstream-YYYYMMDD, cut from master, so master
# and origin are untouched until you look: if refresh passes, fast-forward
# (merge) or reset (rebase, then push --force-with-lease) master to it.
set -eu
cd "$(dirname "$0")/.."
mode=rebase bench=1
for a in "$@"; do
  case $a in
    --merge) mode=merge;;
    --no-bench) bench=0;;
    *) echo "usage: $0 [--merge] [--no-bench]" >&2; exit 2;;
  esac
done
[ -z "$(git status --porcelain --untracked-files=no)" ] || {
  echo "commit or stash your changes first" >&2; exit 1; }
git remote get-url upstream >/dev/null 2>&1 ||
  git remote add upstream https://github.com/BLAKE3-team/BLAKE3.git
git fetch upstream --tags
base=$(git merge-base master upstream/master)
new=$(git rev-list --count "$base..upstream/master")
echo "upstream/master has $new commit(s) we do not"
branch="sync/upstream-$(date +%Y%m%d)"
git checkout -B "$branch" master

# Our README.md replaces upstream's, which lives on verbatim in
# README.upstream.md: a conflict on README.md alone keeps ours and refreshes
# README.upstream.md from upstream. Anything else stops for you to resolve.
readme_only() {
  [ "$(git diff --name-only --diff-filter=U)" = "README.md" ]
}
take_readme() {  # $1: --theirs during a rebase (our commit), --ours in a merge
  git show upstream/master:README.md > README.upstream.md
  git checkout "$1" README.md
  git add README.md README.upstream.md
}
if [ "$mode" = merge ]; then
  if ! git merge --no-edit upstream/master; then
    readme_only || { echo "merge conflicts beyond README.md: resolve them, then run scripts/refresh.sh" >&2; exit 1; }
    take_readme --ours
    git commit --no-edit
  fi
else
  if ! git rebase upstream/master; then
    while [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; do
      readme_only || { echo "rebase conflicts beyond README.md: resolve them, git rebase --continue, then run scripts/refresh.sh" >&2; exit 1; }
      take_readme --theirs
      GIT_EDITOR=true git rebase --continue || true
    done
  fi
fi
git show upstream/master:README.md > README.upstream.md
if ! git diff --quiet -- README.upstream.md; then
  git add README.upstream.md
  git commit -m "README.upstream.md: upstream's README as of $(git rev-parse --short upstream/master)"
fi
echo "on $branch ($mode of upstream/master); refreshing"
if [ "$bench" = 1 ]; then scripts/refresh.sh; else scripts/refresh.sh --no-bench; fi
cat <<MSG

All checks passed on $branch. To take it:
  git checkout master && git merge --ff-only $branch        (after --merge)
  git checkout master && git reset --hard $branch            (after a rebase)
  git push --force-with-lease origin master                  (rebase only)
MSG
