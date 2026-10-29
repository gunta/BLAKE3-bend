# turboblake

BLAKE3, turbocharged: the official [`b3sum`](https://crates.io/crates/b3sum)
and [`blake3`](https://crates.io/crates/blake3) crate (1.8.7) in one crate,
a drop-in for `b3sum` and `sha256sum` on the command line and for `blake3`
in your code. Every flag, every output format, every error message and every
API is upstream's (upstream's own tests pass), and many files and big ones
are hashed at once by a [Bend2](https://bend-lang.com) engine: opened in
parallel, mapped or read, files not in the page cache streamed at SSD speed,
every file's tree on every core. BLAKE3 is a Merkle tree, and Bend2 runs
tree-shaped work in parallel on every CPU core and the GPU.

## The command

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

Each batch of files goes to whichever is faster on it: the engine for many
files, several big ones, or a big one not in the page cache; upstream's code
for a few small files and for one big file in the cache, where page faults
bound both alike. `--check` hashes its files the same way, a batch of lines
at a time. stdin and `--no-mmap` read big blocks while the block before
hashes on every core (upstream reads 64 KiB at a time on one). `--keyed`,
`--derive-key`, `--length` and `--seek` run upstream's code. rayon's threads
start only when a file needs them, and a small file hashes on one thread.
`TURBOBLAKE=0` turns the engine off. Error messages start with
`turboblake:`, or `b3sum:` for the `replace` install.

## The library

```toml
[dependencies]
turboblake = "1.8"
```

The library is named `blake3`, so your code keeps `use blake3::…`.
`blake3::hash`, `Hasher::update` and `update_rayon` go through the engine
past a size it calibrates at the first big input (about 256 KiB on an Apple
M5 Pro), in every mode (keyed hashing and key derivation too); below that,
and in `no_std` builds, it is upstream's code. Without the command line's
dependencies:

```toml
turboblake = { version = "1.8", default-features = false, features = ["std"] }
```

To swap it in for every crate in a dependency graph (iroh, for example),
generate the library as a package named `blake3` and patch it in (see
[bend/rust](https://github.com/gunta/turboblake/tree/master/bend/rust)).
`TURBOBLAKE_THREADS=<n>` caps the engine's threads, `TURBOBLAKE_TRACE=1`
prints what it did.

On a GPU (ADR 0017), loaded at run time (Metal on macOS, CUDA through
libcuda elsewhere; nothing changes without one):

```rust
let mut h = blake3::Hasher::new();
unsafe { h.update_cuda(tensor_ptr, len, std::ptr::null_mut()) };   // CUDA device memory
unsafe { h.update_metal(mtl_buffer, offset, len) };                 // an id<MTLBuffer>
let mut m = blake3::gpu::Memory::new(1 << 30).unwrap();              // memory the GPU reads
blake3::hash(&m);                                                   // split between CPU and GPU
```

`blake3::gpu::backend()` says which one runs; `TURBOBLAKE_GPU=0` turns it
off, `TURBOBLAKE_NO_GPU=1` builds without it.

## Speed

Against the official `b3sum` on an Apple M5 Pro: a 101.5 GB DeepSeek-V4.1
model shard bigger than RAM in 7.65 s against 211 s; 2,000 x 64 KiB files
10.9x faster, 8,000 cargo source files 4.0x, stdin and `--no-mmap` 9x on
1 GiB, and never slower on any case measured (ADR 0016). Benchmarks and
method:
[gunta.github.io/turboblake](https://gunta.github.io/turboblake/).

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
