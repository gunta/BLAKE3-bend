# turboblake (Python)

The `blake3` module, API-compatible with the Rust-based
[`blake3`](https://pypi.org/project/blake3/) on PyPI, built on
libblake3-bend: the official BLAKE3 C library whose big inputs are hashed on
every core by a [Bend2](https://bend-lang.com) engine. blake3-py's own test
suite passes.

```bash
pip uninstall blake3 && pip install turboblake
```

```python
from blake3 import blake3

blake3(b"hello world").hexdigest()
blake3(data, key=key).digest(length=64, seek=0)
hasher = blake3(derive_key_context="example.com 2026-10-26 session keys")
hasher.update_mmap("big.iso")
```

Your code keeps `from blake3 import blake3`. `max_threads` is accepted and
ignored, as the upstream docs allow: the engine takes any update big enough
to beat the trip to it, on every core. Building from source needs a C
compiler, and clang for the engine (set `CC=clang` if gcc is the default);
without clang it builds on the official C alone.

The extension is blake3-py's C implementation (`c_impl/blake3module.c`, by
Jack O'Connor, CC0-1.0 OR Apache-2.0), with `update_mmap` mapping the file.
Its tests (`tests/`) are blake3-py's.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as
BLAKE3. The engine contains the Bend2 runtime, Apache-2.0.
