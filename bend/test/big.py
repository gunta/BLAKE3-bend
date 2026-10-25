#!/usr/bin/env python3
"""Big-file test: Bend b3sum vs the official b3sum on sparse files whose
sizes sit on and around the 1 GiB segment boundaries (and 4 GiB, past the
old 32-bit length), with random bytes stamped at the edges of each segment.

usage: test/big.py [dir]   (sparse files: they take almost no disk)
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REF = ROOT / "b3sum" / "target" / "release" / "b3sum"
BEND = ROOT / "bend" / "build" / "b3sum"
G = 1 << 30
SIZES = [G - 1, G, G + 1, G + 1024, 2 * G - 1, 2 * G, 2 * G + 1, 3 * G + 5000,
         4 * G - 1, 4 * G, 4 * G + 1, 5 * G + 1023, 8 * G + 12345]

d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/b3big")
d.mkdir(parents=True, exist_ok=True)
paths = []
for n in SIZES:
    p = d / f"sparse_{n}.bin"
    if not p.exists() or p.stat().st_size != n:
        with open(p, "wb") as f:
            f.truncate(n)
            for off in sorted({0, n - 1} | {k * G + dx for k in range(1, n // G + 1)
                                            for dx in (-4096, -1, 0, 1, 4096)}):
                if 0 <= off < n:
                    f.seek(off)
                    f.write(os.urandom(min(64, n - off)))
    paths.append(str(p))
want = subprocess.run([str(REF)] + paths, capture_output=True, check=True).stdout
got = subprocess.run([str(BEND)] + paths, capture_output=True, check=True).stdout
if got != want:
    for a, b in zip(want.decode().splitlines(), got.decode().splitlines()):
        print(("ok  " if a == b else "BAD ") + b)
    sys.exit(1)
print(f"{len(paths)}/{len(paths)} big files match ({SIZES[0]} .. {SIZES[-1]} bytes)")
