#!/usr/bin/env python3
"""Spans past 4 TiB: test/hi.bend's CVs, every tree, against the official
crate's subtree CVs at the same input offset (test/hiref, hazmat). The
cases are read from hi.bend's main.

usage: test/hi.py
"""
import pathlib
import re
import subprocess
import sys

BEND = pathlib.Path(__file__).resolve().parents[1]
cases = re.findall(r'one\("(\w+)", (\d+), (\d+), (\d+)\)', (BEND / "test" / "hi.bend").read_text())
args = []
for name, n, cb, hi in cases:
    args += [name, n, str(int(hi) << 32 | int(cb))]
subprocess.run(["sh", str(BEND / "build.sh"), str(BEND / "test" / "hi.bend")], check=True,
               stdout=subprocess.DEVNULL)
subprocess.run(["cargo", "build", "--release", "-q"], cwd=BEND / "test" / "hiref", check=True)
want = subprocess.run([str(BEND / "test" / "hiref" / "target" / "release" / "hiref")] + args,
                      capture_output=True, check=True, text=True).stdout.split("\n")
got = subprocess.run([str(BEND / "test" / "build" / "hi")], capture_output=True, check=True,
                     text=True).stdout.split("\n")
def cvs(lines):
    out = set()
    for l in filter(None, lines):
        name, *rest = l.split()
        out |= {(name, rest[i], rest[i + 1]) for i in range(0, len(rest), 2)}
    return out
want, got = cvs(want), cvs(got)
for g in sorted(got - want):
    print("BAD {} {} {}".format(*g))
n = len(want & got)
if got != want:
    sys.exit(f"{n}/{len(want)} spans past 4 TiB match")
print(f"{n}/{len(want)} spans past 4 TiB match ({len(cases)} cases x cpu, gpu, ob, keyed, tree1)")
