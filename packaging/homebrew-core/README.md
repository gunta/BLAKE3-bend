# turboblake for homebrew-core

`brew install turboblake`, without the tap, needs this formula in
[homebrew-core](https://github.com/Homebrew/homebrew-core). Until then the tap serves the
prebuilt release archives: `brew install gunta/tap/turboblake`.

This is the source build homebrew-core asks for, from the crates.io release. It builds and
passes `brew test` and `brew audit --new --strict --online` on macOS arm64, and ties the
tap's prebuilt binary (1 GiB file and 2,000 small files, 2026-10-29). Its Linux build has not
been run yet; the homebrew-core pull request's CI runs it.

Homebrew's compiler shims drop `-O3` and `-mcpu=native`, so the formula asks for `-O3` back
(`ENV.O3`) and leaves the CPU to the bottle's baseline (`TURBOBLAKE_PORTABLE`). On Linux it
points `CC` at Homebrew's clang, because the engine builds only under clang. The command line
stays on the CPU (`TURBOBLAKE_NO_GPU`).

## Before submitting

Homebrew's [acceptance policy](https://docs.brew.sh/Package-Acceptance-Policy#notability):

- the repository must be at least 30 days old: gunta/turboblake was created 2026-10-25, so
  it qualifies from 2026-11-24;
- a submission by the repository owner needs 90 forks, 90 watchers or 225 stars (30, 30 or
  75 if someone else submits it);
- the numbers count for the canonical repository, not a code-hosting fork. GitHub lists
  gunta/turboblake as a fork of BLAKE3-team/BLAKE3; GitHub Support can detach it from the
  fork network. A fork under its own name is allowed.

## Submitting

On each release, update `url` and `sha256` (`shasum -a 256` of the `.crate`), then:

```bash
brew bump-formula-pr --url https://static.crates.io/crates/turboblake/turboblake-VERSION.crate turboblake
```

For the first submission, open a pull request that adds this file as
`Formula/t/turboblake.rb` in Homebrew/homebrew-core.
