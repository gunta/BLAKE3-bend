# turboblake

BLAKE3, turbocharged: the official [`b3sum`](https://crates.io/crates/b3sum)
(1.8.7) on [`blake3-bend`](https://crates.io/crates/blake3-bend), a drop-in
for `b3sum` and `sha256sum`. Every flag, every output format and every
error message is upstream's (upstream's own CLI tests pass), and in the
default mode many files and big ones are hashed at once by a
[Bend2](https://bend-lang.com) engine: opened in parallel, mapped or read,
files not in the page cache streamed at SSD speed, every file's tree on
every core. BLAKE3 is a Merkle tree, and Bend2 runs tree-shaped work in
parallel on every CPU core and the GPU.

```bash
brew install gunta/tap/turboblake
```

```bash
cargo install turboblake
```

Homebrew installs a prebuilt binary (macOS and Linux, arm64 and x86-64);
`cargo install` builds from source, tuned for your CPU, and needs clang
(Apple's, or LLVM 19+). `cargo binstall turboblake` fetches the prebuilt
binaries through cargo.

```bash
turboblake FILE...           # one "<hash>  <name>" line per file, as b3sum prints
turboblake FILE... > B3SUMS  # write checksums
turboblake --check B3SUMS    # verify them, like sha256sum -c
```

To make it your `b3sum` (it takes the place of the official one, if you
had installed that with cargo):

```bash
cargo install turboblake --features replace --force
```

or keep both and alias it: `alias b3sum=turboblake`.

`--keyed`, `--derive-key`, `--length`, `--seek`, `--check`, `--no-mmap` and
stdin go through upstream's code (on blake3-bend, so a big input still
takes every core); `BLAKE3_BEND=0` turns the engine off. Error messages
start with `turboblake:`, or `b3sum:` for the `replace` install.

Against the official `b3sum` on an Apple M5 Pro: a 101.5 GB DeepSeek-V4.1
model shard bigger than RAM in 7.65 s against 211 s; 2,000 x 64 KiB files
10.7x faster, 8,000 cargo source files 3.5x. Benchmarks and method:
[gunta.github.io/BLAKE3-bend](https://gunta.github.io/BLAKE3-bend/).

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
