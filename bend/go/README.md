# BLAKE3 for Go, on libblake3-bend

Two drop-in packages over libblake3-bend, the official BLAKE3 C library
whose big inputs are hashed on every core by a [Bend2](https://bend-lang.com)
engine:

| was | now |
|---|---|
| `lukechampine.com/blake3` | `github.com/gunta/BLAKE3-bend/bend/go` |
| `github.com/zeebo/blake3` | `github.com/gunta/BLAKE3-bend/bend/go/zeebo` |

```bash
go get github.com/gunta/BLAKE3-bend/bend/go
```

```go
import blake3 "github.com/gunta/BLAKE3-bend/bend/go"

sum := blake3.Sum256(data)
h := blake3.New(64, key) // hash.Hash; h.XOF() for extended output
sums, errs := blake3.HashFiles(paths) // many files at once, as the b3bend command
```

Same functions, types and outputs, with three additions (`NewDeriveKey`,
`Hasher.Clone`, `HashFiles`). One deliberate difference:
lukechampine.com/blake3 v1.4.1 returns wrong bytes after `OutputReader.Seek`
to an offset that is not a multiple of 1024; this package returns BLAKE3's
(the official crate agrees).

Needs cgo, on macOS or Linux. The engine is linked prebuilt
(`engine_<os>_<arch>.syso`: clang with the vectorizer flags cgo will not
pass), for the platforms that have one checked in: darwin/arm64 (Apple M1
and later) and darwin/amd64 (`gen.sh` on a Mac), linux/amd64 (x86-64-v3,
AVX2) and linux/arm64 (`bend/bench/modal_linux.py --steps go`). Elsewhere
cgo compiles the engine at plain flags (`c_engine.c`), slower and still on
every core.

On an Apple M5 Pro, `Sum256` of 1 GiB in memory: 33 ms, against 107 ms
(lukechampine.com/blake3), 1237 ms (github.com/zeebo/blake3) and 383 ms
(crypto/sha256); `cd bench && go run .` re-runs it. `go test` checks the
official vectors in every mode and both reference modules on random inputs.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
