# Releasing turboblake

One version (`bend/VERSION`) for every package, one tag to publish them all
(ADR 0020).

```bash
scripts/release/prepare.sh 1.8.9   # set the version everywhere, regenerate the crate, dry-run each package, commit
git push origin master             # turboblake-build builds and tests every package on every platform
scripts/release/tag.sh             # once that passed: tag (signed if git has a key), confirm, push
```

The tag runs `.github/workflows/turboblake-release.yml`: the same build, a
draft GitHub release with every file, `SHA256SUMS` and build provenance
attestations, then crates.io, npm and PyPI, then the published release, the
Go module tag, the Homebrew tap and a homebrew-core pull request. Every
publish step skips a version that is already there: if a step fails, fix
the cause and re-run the failed jobs.

## What gets built

| script | builds | where (CI) |
|---|---|---|
| `build-cli.sh TARGET OUT` | `turboblake-<v>-<target>.tar.gz`/`.zip`, checked against the official vectors | runners (macOS, Windows), containers (Linux) |
| `build-lib.sh TARGET OUT` | `libturboblake-<v>-<target>.tar.gz` (CMake: static, shared, pkg-config, CMake package) | same |
| `build-npm.sh PLATFORM OUT` | `prebuilds/<platform>/turboblake.node`, after the package's tests | same |
| `check-old-cpu.sh BIN` | proves an x86-64 binary runs on a CPU without AVX (qemu) | Linux x86-64 |
| `smoke-npm.sh TGZ` | installs the packed npm package and requires the native addon | every OS |
| `formulas.py` | the Homebrew formulas from `SHA256SUMS` | the release |
| `version.py` | sets or checks the version in every manifest | everywhere |

Linux builds run in `quay.io/pypa/manylinux_2_28_*` (glibc 2.28) or
`alpine:3.22` (musl) after `setup-linux.sh`, so they run locally the same
way:

```bash
docker run --rm -v "$PWD:/w" -w /w quay.io/pypa/manylinux_2_28_aarch64 \
  sh -c 'scripts/release/setup-linux.sh cli && scripts/release/build-cli.sh aarch64-unknown-linux-gnu dist'
```

## One-time setup

- **GitHub**: an environment named `release` (Settings, Environments); add
  required reviewers to approve each publish by hand. Settings, Actions,
  General: allow GitHub Actions to create pull requests (for the
  homebrew-core formula).
- **crates.io**: on the `turboblake` crate, Settings, Trusted Publishing:
  repository `gunta/turboblake`, workflow `turboblake-release.yml`,
  environment `release`.
- **PyPI**: a pending trusted publisher for the project `turboblake`, with
  the same repository, workflow and environment.
- **npm**: the package `turboblake`, Settings, Trusted Publisher: GitHub
  Actions, the same repository, workflow and environment. (npm only offers
  that for a package that exists: a brand-new package's first version is
  published by hand, as 1.8.8 was.)
- **Homebrew**: a fine-grained token with Contents: read and write on
  `gunta/homebrew-tap` only, as the `HOMEBREW_TAP_TOKEN` secret of the
  repository. Without it the release leaves the tap alone and prints the
  formulas.

## Checking a release

```bash
gh attestation verify turboblake-1.8.8-x86_64-unknown-linux-gnu.tar.gz --repo gunta/turboblake
npm audit signatures            # in a project that installed turboblake
```
