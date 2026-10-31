---
name: migrate-to-turboblake-go
description: Move a Go module from lukechampine.com/blake3 or github.com/zeebo/blake3 to turboblake's drop-in packages, which hash big inputs on every CPU core through cgo. Use when the user asks to speed up BLAKE3 in Go or switch to turboblake.
---

# Migrate a Go module to turboblake

Two drop-in packages over libturboblake (the official BLAKE3 C library, big inputs
hashed on every core by a Bend2 engine), each with the same functions, types and outputs
as the package it replaces:

| was | now |
|---|---|
| `lukechampine.com/blake3` | `github.com/gunta/turboblake/bend/go` |
| `github.com/zeebo/blake3` | `github.com/gunta/turboblake/bend/go/zeebo` |

## 1. Find what uses BLAKE3

```bash
grep -rlnE '"(lukechampine\.com/blake3|github\.com/zeebo/blake3)"' --include=*.go . | grep -v /vendor/
grep -nE 'lukechampine\.com/blake3|zeebo/blake3' go.mod
go mod why -m lukechampine.com/blake3 github.com/zeebo/blake3 2>/dev/null
```

If only a dependency imports them, the module cannot swap its imports; say so (a `replace`
directive cannot point one module path at a different package API).

## 2. Check cgo first

The packages need cgo (a C compiler and `CGO_ENABLED=1`). Look for `CGO_ENABLED=0` in
Dockerfiles, Makefiles, `.goreleaser.yaml` and CI before switching: static `scratch`/
distroless builds with cgo off will not compile. If the project must stay cgo-free, stop
and tell the user turboblake is not a fit for that build.

## 3. Swap

```bash
go get github.com/gunta/turboblake/bend/go@v{{version}}
```

Rewrite the imports, keeping the package name `blake3` so call sites do not change:

```go
// was: import "lukechampine.com/blake3"
import blake3 "github.com/gunta/turboblake/bend/go"

// was: import "github.com/zeebo/blake3"
import blake3 "github.com/gunta/turboblake/bend/go/zeebo"
```

```bash
gofmt -w $(grep -rlE 'turboblake/bend/go' --include=*.go .)
go mod tidy
```

`Sum256`, `Sum512`, `New(size, key)`, `DeriveKey`, `Hasher` (`hash.Hash`), `XOF()` /
`OutputReader` (lukechampine) and zeebo's `New`, `NewKeyed`, `DeriveKey`, `Digest` keep their
signatures. Additions: `NewDeriveKey`, `Hasher.Clone`, `HashFiles(paths)`.

One deliberate difference: lukechampine.com/blake3 v1.4.1 returns wrong bytes after
`OutputReader.Seek` to an offset that is not a multiple of 1024; this package returns
BLAKE3's. If a test pinned the old bytes, the test was wrong.

## 4. Verify

```go
sum := blake3.Sum256(nil)
if hex.EncodeToString(sum[:]) != "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262" { panic("empty") }
in := make([]byte, 1024)
for i := range in { in[i] = byte(i % 251) }
sum = blake3.Sum256(in)
if hex.EncodeToString(sum[:]) != "42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7" { panic("1024") }
```

Then `go vet ./... && go test ./...`. `TURBOBLAKE_TRACE=1` prints the engine's calibration
and jobs to stderr once an input is big (a few MiB).

## Know before you ship

- The engine is linked prebuilt for darwin/arm64, darwin/amd64, linux/amd64 and
  linux/arm64. Other Unix systems compile it through cgo at plain flags (slower, still
  every core). Windows (MinGW) gets the official BLAKE3 C alone.
- Cross-compiling now needs a C cross-compiler (zig cc works) for each target.
- linux/amd64 uses AVX2 where the CPU has it; older CPUs run the official C.
- It pays off from about 256 KiB per call; many tiny hashes pay a cgo call each.
- Run-time switches: `TURBOBLAKE=0` (engine off), `TURBOBLAKE_THREADS=<n>`.
- Rolling back: revert the imports and `go mod tidy`.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3.
Docs: https://gunta.github.io/turboblake/install/go/
