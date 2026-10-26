#!/usr/bin/env python3
"""Past 4 TiB: Bend b3sum on a sparse file of 4 TiB + 1 GiB + 12345 bytes,
with random bytes stamped around the 4 TiB mark (chunk counter 2^32, where
the counter's high word turns 1) and at the ends, against the official
crate. Reading 4.4 TB through the official b3sum takes half an hour, so the
reference (test/hiref --file) reads only the file's data and hashes each
1 GiB segment as a subtree at its offset (hazmat): a few minutes of every
core. Bend reads every byte, as for any file.

usage: test/huge.py [dir]   (sparse: the file takes a few blocks of disk)
"""
import os
import pathlib
import subprocess
import sys
import time

BEND = pathlib.Path(__file__).resolve().parents[1]
G = 1 << 30
N = (1 << 42) + G + 12345

d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/b3huge")
d.mkdir(parents=True, exist_ok=True)
p = d / f"sparse_{N}.bin"
if not p.exists() or p.stat().st_size != N:
    with open(p, "wb") as f:
        f.truncate(N)
        for off in sorted({0, N - 1, (1 << 42) - 1024} |
                          {k * G + dx for k in (4095, 4096, 4097) for dx in (-4096, -1, 0, 1, 4096)}):
            if 0 <= off < N:
                f.seek(off)
                f.write(os.urandom(min(64, N - off)))
subprocess.run(["cargo", "build", "--release", "-q"], cwd=BEND / "test" / "hiref", check=True)
t = time.time()
got = subprocess.run([str(BEND / "build" / "b3sum"), str(p)], capture_output=True, check=True).stdout
tb = time.time() - t
t = time.time()
want = subprocess.run([str(BEND / "test" / "hiref" / "target" / "release" / "hiref"), "--file", str(p)],
                      capture_output=True, check=True).stdout
tr = time.time() - t
print(f"bend    {got.decode().split()[0]}  ({tb:.0f} s, {N / tb / 1e9:.1f} GB/s)")
print(f"crate   {want.decode().split()[0]}  ({tr:.0f} s, data extents only)")
if got != want:
    sys.exit(f"MISMATCH on {N} bytes")
print(f"match: {N} bytes (4 TiB + 1 GiB + 12345), past 32-bit chunk counters")
