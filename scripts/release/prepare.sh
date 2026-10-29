#!/bin/sh
# Step 1 of a release: sets turboblake's version everywhere, regenerates the
# crate from it, checks that every package builds as it will be published,
# and commits "turboblake X.Y.Z". Nothing leaves this machine; push the
# commit and let CI (turboblake-build.yml) build and test every package on
# every platform, then run tag.sh.
#   scripts/release/prepare.sh X.Y.Z
set -eu
. "$(dirname "$0")/common.sh"
new=${1:?usage: prepare.sh X.Y.Z}
cd "$root"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "commit or stash your changes first"
git rev-parse -q --verify "refs/tags/turboblake-v$new" >/dev/null && die "turboblake-v$new exists already"

say "== version $version -> $new"
python3 scripts/release/version.py set "$new"
bend/rust/gen.sh >/dev/null           # bend/crate, with the new version
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
say "committed turboblake $new. Next: push it, wait for turboblake-build to pass, then scripts/release/tag.sh"
