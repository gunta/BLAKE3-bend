"""BLAKE3, API-compatible with the Rust-based blake3 module on PyPI, on
libblake3-bend: big inputs are hashed on every core by a Bend2 engine."""

from ._blake3 import __version__, blake3

__all__ = ["blake3", "__version__"]
