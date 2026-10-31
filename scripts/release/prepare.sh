#!/bin/sh
# A release, in one command: sets turboblake's version everywhere,
# regenerates the crate from it, checks that every package builds as it will
# be published, commits "turboblake X.Y.Z" and pushes it to master. CI does
# the rest: turboblake-build.yml builds and tests every package on every
# platform, and when it passes turboblake-release.yml publishes them all
# (crates.io, npm, PyPI, GitHub release, Go, Homebrew). --no-push stops
# after the commit.
#   scripts/release/prepare.sh X.Y.Z [--no-push]
set -eu
. "$(dirname "$0")/common.sh"
new=${1:?usage: prepare.sh X.Y.Z [--no-push]}
push=yes; [ "${2:-}" = --no-push ] && push=no
cd "$root"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "commit or stash your changes first"
if [ $push = yes ]; then
  git fetch -q origin master
  [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" ] || die "HEAD is not origin/master: release from master as it is on GitHub"
fi
git rev-parse -q --verify "refs/tags/turboblake-v$new" >/dev/null && die "turboblake-v$new exists already"

say "== version $version -> $new"
python3 scripts/release/version.py set "$new"
bend/rust/gen.sh >/dev/null           # bend/crate, with the new version
(cd bend/crate && cargo update -q -w --offline)  # its own entry in Cargo.lock, nothing else
python3 scripts/release/version.py check

say "== crates.io: cargo publish --dry-run"
(cd bend/crate && cargo publish --dry-run --locked --allow-dirty -q)
say "== npm: the package's files"
(cd bend/node && npm pack --dry-run --json --ignore-scripts >/dev/null)
say "== PyPI: the sdist"
tmp=$(mktemp -d)
python3 -m build --sdist --outdir "$tmp" bend/python >/dev/null 2>&1 || uv build -q --sdist -o "$tmp" bend/python
rm -rf "$tmp"

git add -A bend/VERSION bend/crate bend/node/package.json bend/python/pyproject.toml bend/python/setup.py
git commit -q -m "turboblake $new"
if [ $push = no ]; then
  say "committed turboblake $new; git push origin HEAD:master releases it"
  exit 0
fi
git push -q origin HEAD:master
repo=$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')
say "pushed turboblake $new: https://github.com/$repo/actions builds it, then publishes it everywhere"
