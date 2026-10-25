#!/usr/bin/env python3
"""Compares `len hash` lines on stdin with test_vectors/test_vectors.json."""
import json, pathlib, sys

root = pathlib.Path(__file__).resolve().parents[2]
cases = json.loads((root / "test_vectors" / "test_vectors.json").read_text())["cases"]
want = {c["input_len"]: c["hash"][:64] for c in cases}
seen = bad = 0
for line in sys.stdin:
    n, h = line.split()
    n = int(n)
    if n in want:
        seen += 1
        if want[n] != h:
            bad += 1
            print(f"MISMATCH len={n}\n  got  {h}\n  want {want[n]}")
print(f"{seen - bad}/{seen} official vectors match")
sys.exit(1 if bad or seen == 0 else 0)
