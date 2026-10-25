#!/usr/bin/env python3
"""End-to-end race: official b3sum vs the Bend b3sum, file workloads.

Runs every command of a workload once per round, in an order that flips each
round, so drift on a busy machine hits both sides alike; reports the median
and the minimum wall time. Checks that both print the same bytes first.

usage: bench/race.py [rounds] [workload ...]
"""

import os
import pathlib
import statistics
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data"
REF = ROOT / "b3sum" / "target" / "release" / "b3sum"
BEND = ROOT / "bend" / "build" / "b3sum"


def files(pattern):
    return sorted(str(p) for p in DATA.glob(pattern))


WORKLOADS = {
    "1 GiB file": lambda: [str(DATA / "big_1g.bin")],
    "64 MiB file": lambda: [str(DATA / "mid_64m.bin")],
    "10k x 4 KiB": lambda: files("small4k/*"),
    "2k x 64 KiB": lambda: files("small64k/*"),
    "5 GiB file": lambda: [str(DATA / "huge_5g.bin")],
}


def run(cmd):
    t = time.perf_counter()
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return (time.perf_counter() - t) * 1000


def race(name, args, rounds):
    sides = {"b3sum": [str(REF)] + args, "bend": [str(BEND)] + args}
    outs = {k: subprocess.run(v, capture_output=True).stdout for k, v in sides.items()}
    if outs["b3sum"] != outs["bend"]:
        sys.exit(f"{name}: outputs differ")
    for cmd in sides.values():
        for _ in range(2):
            run(cmd)
    times = {k: [] for k in sides}
    order = list(sides)
    for _ in range(rounds):
        for k in order:
            times[k].append(run(sides[k]))
        order.reverse()
    med = {k: statistics.median(v) for k, v in times.items()}
    lo = {k: min(v) for k, v in times.items()}
    ratio = med["b3sum"] / med["bend"]
    verdict = f"bend {ratio:.2f}x faster" if ratio >= 1 else f"bend {1 / ratio:.2f}x slower"
    print(f"| {name:<12} | {med['b3sum']:8.1f} | {lo['b3sum']:8.1f} | "
          f"{med['bend']:8.1f} | {lo['bend']:8.1f} | {verdict} |", flush=True)


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    names = sys.argv[2:] or [n for n in WORKLOADS if n != "5 GiB file"]
    print(f"{rounds} interleaved rounds, wall ms "
          f"(load avg {os.getloadavg()[0]:.1f})\n")
    print("| workload     | b3sum md | b3sum lo |  bend md |  bend lo | result |")
    print("|--------------|----------|----------|----------|----------|--------|")
    for n in names:
        race(n, WORKLOADS[n](), rounds)


if __name__ == "__main__":
    main()
