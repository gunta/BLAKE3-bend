#!/usr/bin/env python3
"""Compares `len hash` lines on stdin with test_vectors/test_vectors.json.
Blank lines are skipped; `same ...` / `DIFF ...` lines (test/split.bend's
own comparisons) are counted, and any DIFF fails."""
import json, pathlib, sys

root = pathlib.Path(__file__).resolve().parents[2]
cases = json.loads((root / "test_vectors" / "test_vectors.json").read_text())["cases"]
want = {c["input_len"]: c["hash"][:64] for c in cases}
seen = bad = same = diff = 0
for line in sys.stdin:
    f = line.split()
    if not f:
        continue
    if f[0] in ("same", "DIFF"):
        same += f[0] == "same"
        diff += f[0] == "DIFF"
        if f[0] == "DIFF":
            print(line.rstrip())
        continue
    n, h = f
    n = int(n)
    if n in want:
        seen += 1
        if want[n] != h:
            bad += 1
            print(f"MISMATCH len={n}\n  got  {h}\n  want {want[n]}")
print(f"{seen - bad}/{seen} official vectors match")
if same or diff:
    print(f"{same}/{same + diff} big cases same as the CPU tree")
sys.exit(1 if bad or diff or seen == 0 else 0)
