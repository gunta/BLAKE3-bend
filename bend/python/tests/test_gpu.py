# turboblake: the GPU entry points (ADR 0017) against the CPU, when this
# machine has a GPU backend. GPU memory comes from the library's own test
# helper (tbg_upload) through ctypes.
import ctypes
import random

import pytest

import blake3

pytestmark = pytest.mark.skipif(blake3.gpu() is None, reason="no GPU backend")


def upload(data, pad, gpu_only):
    so = ctypes.CDLL(blake3._blake3.__file__)
    so.tbg_upload.restype = ctypes.c_void_p
    so.tbg_upload.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int]
    so.tbg_drop.argtypes = [ctypes.c_void_p]
    dev = so.tbg_upload(data, len(data), pad, gpu_only)
    assert dev
    return dev, so.tbg_drop


def test_gpu_memory() -> None:
    rnd = random.Random(3)
    for n in [0, 1, 1024, 1025, 65537, 1 << 20, (16 << 20) + 5]:
        data = rnd.randbytes(n)
        for gpu_only in (1, 0):
            dev, drop = upload(data, 7, gpu_only)
            for key in (None, b"k" * 32):
                h = blake3.blake3(key=key) if key else blake3.blake3()
                if blake3.gpu() == "metal":
                    h.update_metal(dev, 7, n)
                else:
                    h.update_cuda(dev + 7, n)
                want = blake3.blake3(data, key=key) if key else blake3.blake3(data)
                assert h.hexdigest(length=40) == want.hexdigest(length=40), (n, gpu_only, key)
            drop(dev)
