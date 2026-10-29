#!/bin/sh
# Step 2 of a release: tags the release commit and pushes the tag, which
# starts turboblake-release.yml (every registry, the GitHub release,
# Homebrew). It refuses unless the tree is clean, HEAD is origin/master,
# every package carries the version, the tag is new, and turboblake-build
# passed on this very commit. The tag is signed when git has a signing key.
#   scripts/release/tag.sh [--yes]
set -eu
. "$(dirname "$0")/common.sh"
cd "$root"
tag="turboblake-v$version"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "the tree has changes"
git fetch -q origin master --tags
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" ] || die "HEAD is not origin/master: push the release commit first"
python3 scripts/release/version.py check "$tag"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && die "$tag exists already"
git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1 && die "$tag exists on origin"

sha=$(git rev-parse HEAD)
# the repository origin points at (gh would otherwise pick the upstream of a fork)
repo=$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')
ci=$(gh run list --repo "$repo" --commit "$sha" --workflow turboblake-build.yml --json conclusion,status \
  --jq '[.[] | select(.status == "completed")][0].conclusion' 2>/dev/null || true)
[ "$ci" = success ] || die "turboblake-build has not passed on $sha (${ci:-no completed run}); see gh run list --repo $repo --commit $sha"

if [ -n "$(git config user.signingkey || true)" ]; then sign=-s; else sign=-a; fi
git tag $sign "$tag" -m "turboblake $version"
say "tagged $sha as $tag"
if [ "${1:-}" != --yes ]; then
  printf 'Push %s to origin? This publishes turboblake %s to every registry. [y/N] ' "$tag" "$version" >&2
  read -r answer
  [ "$answer" = y ] || [ "$answer" = Y ] || { say "not pushed (git push origin $tag when ready)"; exit 0; }
fi
git push origin "refs/tags/$tag"
say "pushed $tag: gh run watch \$(gh run list --workflow turboblake-release.yml -L1 --json databaseId -q '.[0].databaseId')"
