# BLAKE3 for Go, on libturboblake

Two drop-in packages over libturboblake, the official BLAKE3 C library
whose big inputs are hashed on every core by a [Bend2](https://bend-lang.com)
engine:

| was | now |
|---|---|
| `lukechampine.com/blake3` | `github.com/gunta/turboblake/bend/go` |
| `github.com/zeebo/blake3` | `github.com/gunta/turboblake/bend/go/zeebo` |

```bash
go get github.com/gunta/turboblake/bend/go
```

```go
import blake3 "github.com/gunta/turboblake/bend/go"

sum := blake3.Sum256(data)
h := blake3.New(64, key) // hash.Hash; h.XOF() for extended output
sums, errs := blake3.HashFiles(paths) // many files at once, as the turboblake command
```

Same functions, types and outputs, with three additions (`NewDeriveKey`,
`Hasher.Clone`, `HashFiles`). One deliberate difference:
lukechampine.com/blake3 v1.4.1 returns wrong bytes after `OutputReader.Seek`
to an offset that is not a multiple of 1024; this package returns BLAKE3's
(the official crate agrees).

Needs cgo. The engine is linked prebuilt (`engine_<os>_<arch>.syso`: clang
with the vectorizer flags cgo will not pass), for the platforms that have
one checked in: darwin/arm64 (Apple M1 and later), darwin/amd64, linux/amd64
(x86-64-v3: AVX2 where the CPU has it; an older CPU leaves the hashing to
the official C) and linux/arm64 (any ARMv8), all from `DOCKER=1 gen.sh` on a
Mac. Other Unix systems compile the engine through cgo at plain flags
(`c_engine.c`), slower and still on every core. On Windows (cgo with MinGW)
the package is the official BLAKE3 C alone, with its SIMD: no engine there
yet.

On an Apple M5 Pro, `Sum256` of 1 GiB in memory: 41 ms, against 100 ms
(lukechampine.com/blake3), 1144 ms (github.com/zeebo/blake3) and 404 ms
(crypto/sha256); `cd bench && go run .` re-runs it. `go test` checks the
official vectors in every mode and both reference modules on random inputs.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
