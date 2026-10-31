---
name: migrate-to-turboblake-python
description: Move a Python project from the blake3 package on PyPI to turboblake, the drop-in that hashes big inputs on every CPU core (and the GPU) behind the same `blake3` module. Use when the user asks to speed up BLAKE3 hashing in Python, switch to turboblake, or replace blake3 in requirements.txt, pyproject.toml, uv, Poetry or PDM.
---

# Migrate a Python project to turboblake

turboblake installs the same `blake3` module as the `blake3` package on PyPI (blake3-py's
API, its own test suite passes), built on libturboblake: big inputs are hashed on every
core by a Bend2 engine. Code keeps `from blake3 import blake3`; outputs are byte-for-byte
BLAKE3.

Because both packages provide the module `blake3`, they must not be installed together:
remove `blake3`, add `turboblake`. On Windows, where the engine does not run yet,
`turboblake` depends on the official `blake3` and installs that instead, so Windows
users are never slower than upstream.

## 1. Find what uses BLAKE3

```bash
grep -rnE '(^|[^a-z_])blake3([^a-z_0-9]|$)' --include=requirements*.txt --include=pyproject.toml \
  --include=setup.py --include=setup.cfg --include=Pipfile --include=environment.yml .
grep -rlnE '^\s*(import blake3|from blake3 import)' --include=*.py . | head -50
pip show blake3 2>/dev/null | grep -i required-by    # something else needs it?
```

If another installed package requires `blake3`, its resolver will install `blake3` again
next to `turboblake` and one will overwrite the other's module. Tell the user which
package needs it; on macOS and Linux they can keep it out with the tool's override
(uv: `override-dependencies`, pip: install that package with `--no-deps`) since the API
is the same.

## 2. Swap the dependency

Use the project's own tool (look for `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock`,
or plain requirements files):

```bash
# uv
uv remove blake3 && uv add turboblake
# Poetry
poetry remove blake3 && poetry add turboblake
# PDM
pdm remove blake3 && pdm add turboblake
# pip + requirements.txt: replace the blake3 line with turboblake (keep the version style), then
pip uninstall -y blake3 && pip install turboblake
```

In `pyproject.toml` / `setup.py` / `setup.cfg` dependency lists, `blake3>=…` becomes
`turboblake>=1.8`. Keep conda's `blake3` out of `environment.yml` and add
`turboblake` under `pip:`.

## 3. Code

Nothing to change. `blake3(data)`, `key=`, `derive_key_context=`, `update`, `update_mmap`,
`digest(length=, seek=)`, `hexdigest`, `copy`, `reset`, `blake3.digest_size` all work.
`max_threads` is accepted and ignored: big updates already use every core, so
`max_threads=blake3.AUTO` can stay or go.

Optional, if the project hashes tensors already on a GPU (PyTorch, CuPy):

```python
h = blake3.blake3()
h.update_cuda(t.data_ptr(), t.numel() * t.element_size())  # CUDA device memory
blake3.gpu()   # 'cuda', 'metal' or None
```

## 4. Verify

```bash
python -c "import blake3; print(blake3.__file__, hasattr(blake3, 'gpu'))"
```

`hasattr(blake3, 'gpu')` is `True` when turboblake's module is the one loaded (on macOS and
Linux); `False` means the PyPI `blake3` won (or Windows). Then check outputs against the
official vectors (input: bytes `i % 251`):

```python
from blake3 import blake3
assert blake3(b"").hexdigest() == "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
assert blake3(bytes(i % 251 for i in range(1024))).hexdigest() == \
    "42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7"
```

Run the project's tests. `TURBOBLAKE_TRACE=1 python app.py` shows the engine's
calibration and jobs on stderr once an update is big (a few MiB).

## Know before you ship

- Wheels: macOS and Linux (glibc 2.28+ and musl), arm64 and x86-64, CPython 3.9+. Other
  platforms build the sdist with clang (`CC=clang`); without clang they install the
  official `blake3`.
- Old x86-64 CPUs without AVX2 run the official SIMD code: same results.
- It pays off from about 256 KiB per update; many small hashes run at upstream's speed.
- Run-time switches: `TURBOBLAKE=0` (engine off), `TURBOBLAKE_THREADS=<n>`, `TURBOBLAKE_GPU=0`.
- Rolling back: `remove turboblake`, `add blake3`.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3.
Docs: https://gunta.github.io/turboblake/install/python/
