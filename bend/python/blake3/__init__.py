"""BLAKE3, API-compatible with the Rust-based blake3 module on PyPI, on
libturboblake: big inputs are hashed on every core by a Bend2 engine."""

from ._blake3 import __version__, blake3, gpu

__all__ = ["blake3", "gpu", "__version__"]
