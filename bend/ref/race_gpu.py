#!/usr/bin/env python3
"""Races Bend's GPU path (bench/mem.bend, `hash1!`) against the native Metal
reference over the same in-memory data, interleaved, warm.

usage: race_gpu.py [rounds] [d ...]     (2^d words = 4 * 2^d bytes)
env:   BEND_MEM=path to a built bench/mem   B3METAL=path
       EXTRA="name|argv;..." more contenders, argv with {d} and {reps}

Each round runs every contender once with `reps` hashes and drops the first
two (set-up and warm-up); the table shows the median and best of the rest,
and every digest must match.
"""
import os, pathlib, statistics, subprocess, sys

here = pathlib.Path(__file__).resolve().parent
bend = os.environ.get("BEND_MEM", str(here.parent / "bench/build/mem"))
metal = os.environ.get("B3METAL", str(here / "metal/build/b3metal"))
rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ds = [int(x) for x in sys.argv[2:]] or [22, 24, 26, 28]
reps = 10

specs = [
    f"bend gpu|{bend} +RTS --gpu 2GB -RTS {{d}} {{reps}} 1",
    f"metal K=4|{metal} mem {{d}} {{reps}} 4",
    f"metal, Bend's leaves|{metal} mem {{d}} {{reps}} 0",
] + [s for s in os.environ.get("EXTRA", "").split(";") if s]
cmds = {}
for spec in specs:
    name, argv = spec.split("|", 1)
    cmds[name] = lambda d, argv=argv: argv.format(d=d, reps=reps).split()


def run(argv):
    out = subprocess.run(argv, capture_output=True, text=True, check=True).stdout
    rows = [l.split() for l in out.splitlines() if l.startswith("us ")]
    return [int(float(r[1])) for r in rows[2:]], {r[-1] for r in rows}


for d in ds:
    n = 4 << d
    times = {name: [] for name in cmds}
    digests = set()
    for _ in range(rounds):
        for name, cmd in cmds.items():
            t, h = run(cmd(d))
            times[name] += t
            digests |= h
    ok = "ok" if len(digests) == 1 else f"DIGESTS DIFFER {digests}"
    print(f"{n >> 20} MiB ({ok}, {digests.pop()[:16]}...)")
    for name, t in times.items():
        med = statistics.median(t)
        print(f"  {name:22s} median {med / 1000:7.2f} ms  best {min(t) / 1000:7.2f} ms"
              f"  {n / med / 1e3:6.1f} GB/s")
