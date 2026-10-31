# Taking an upstream update (brief for the coding agent)

`scripts/update-upstream.sh` brought you here. You are on a branch
`sync/upstream-YYYYMMDD` cut from `master`. Upstream BLAKE3 is already merged
into it if it moved (unless the merge stopped on a conflict), and the files
we copy from blake3-py are three-way merged. `.upstream/REPORT.md` has what
moved: for each upstream its commits, the diff of every file we copy or
watch, and our own changes to the copies. `.upstream/sync.log` and
`.upstream/apply.log` say how the merges went.

Your job: decide, change by change, what turboblake adopts; finish the
merge; regenerate; verify; record the decisions; commit on this branch.
Never push, merge into `master`, tag, release or publish: those are the
user's calls.

## What turboblake promises (the test for every decision)

1. **Drop-in.** Same output bytes, same API, same CLI flags and messages as
   what it replaces: official `b3sum` and the `blake3` crate and C library
   (fork), PyPI `blake3` (blake3-py), `lukechampine.com/blake3` and
   `github.com/zeebo/blake3` (bend/go), `@noble/hashes/blake3` (bend/node).
2. **Never slower** than upstream in any case (ADR 0016). Where an upstream
   change makes upstream faster, the dispatch thresholds may need to move.
3. **Proved.** `bend/prove.sh` prints `ALL PROOFS CHECK` (ADR 0007, 0015).

## Deciding

For each upstream that moved, sort its changes:

| change | default |
|---|---|
| a fix to output, safety or soundness | adopt, in every package that carries that code |
| new API, flag or option | adopt in the package that mirrors it; add it to the other bindings only when cheap and natural, and say which |
| a change to an anchor our generators patch (`c/blake3.c`, `src/lib.rs`, `b3sum/src/*`, `Cargo.toml`, `build.rs`) | adopt, and move the anchor in `bend/lib/patch.py`, `bend/rust/patch_crate.py` or `bend/rust/patch_b3sum.py`; never hand-edit generated output (`bend/crate`, `bend/lib/csrc`, `bend/go/csrc`) |
| a speedup in upstream's own SIMD or rayon paths | adopt (turboblake runs those paths for small inputs), then race (below) |
| a minimum toolchain or Python/Go/Node version bump | adopt if our packages can follow; otherwise skip and say why |
| upstream CI, release tooling, docs | skip, except `README.md`, which `sync-upstream.sh` keeps in `README.upstream.md` |
| anything that breaks a promise above | skip, or adapt, and explain |

When unsure, adopt upstream's behavior: being a drop-in wins over our taste.

### Per upstream

- **blake3** (fork). Resolve merge conflicts if `.upstream/sync.log` stopped on
  them (`git status`), then `git commit`. The `bend/` port reimplements the
  compression: a change to the BLAKE3 algorithm or its test vectors (unheard
  of) is a stop-and-ask-the-user. `upstream.py apply` copies the vectors to
  `bend/python/tests` and `bend/go/testdata`.
- **blake3-py** (vendored). Our `blake3module.c` is theirs plus libturboblake
  (update_mmap through the engine, max_threads ignored, the GPU methods):
  keep those, take the rest. Their Rust `src/lib.rs` is what PyPI ships, so a
  new method there means a new method in `blake3module.c` and
  `blake3/__init__.pyi`. Their tests run unchanged against ours.
- **go-lukechampine, go-zeebo, noble-hashes** (api). Nothing is copied. Mirror
  new exported API or changed behavior in the files the report lists; bump
  the version in `go.mod`/`bench/go.mod` or `package.json` devDependencies so
  the benches race the new release. A deliberate difference stays documented
  in the package's README (bend/go/README.md has one).
- **bend2** (toolchain). `bend update` installs it (it pipes curl to sh: ask
  the user first). Then everything Bend emits changes: run verify (it
  regenerates), check SLP still vectorizes the compress8 loops (count `.4s`
  ops with `clang -S`, see ADR 0019), and race.

## Doing

```sh
python3 scripts/upstream/upstream.py apply           # again, after you change course
scripts/upstream/verify.sh                           # regenerate and check every package
python3 scripts/upstream/upstream.py pin NAME        # each upstream you took (not blake3)
python3 scripts/upstream/upstream.py status          # what is left
```

`verify.sh` must pass before you commit. If a change could touch speed
(upstream SIMD, rayon, I/O, a new Bend2), race it: `scripts/refresh.sh`
without `--no-bench` (bend/bench/race.py, daemon.py), the language benches
(`bend/lib/bench.py`, `bend/python/bench.py`, `bend/node/bench.mjs`,
`bend/go/bench`) and `python3 bend/bench/collect.py`. Interleaved medians,
15+ rounds; the machine may be loaded by other work, so say how loaded it was
and suggest re-measuring on a quiet one. A loss to upstream anywhere is a
blocker to report, not to commit around.

## Recording

- Commit in steps on this branch: the merge, each adopted change with what it
  takes and why, regenerated outputs with the change that made them, the pins.
- A decision that changes behavior, API, dispatch or speed gets an ADR
  (`adr/NNNN-*.md`, indexed in `adr/README.md`); routine syncs need none.
- Version: propose the next `bend/VERSION` (`scripts/release/prepare.sh
  X.Y.Z` makes it) but leave the bump and the release to the user.
- Write `.upstream/DECISIONS.md`: one row per upstream change (upstream,
  commit or file, adopted / adapted / skipped, why), then what verify and the
  races said, what is left, and the commands for the user to take the
  branch:

  ```sh
  git checkout master && git merge --ff-only sync/upstream-YYYYMMDD
  git push origin master
  ```

End by printing `.upstream/DECISIONS.md`.
