#!/usr/bin/env python3
"""Daemon race: start-up excluded. Each implementation runs as one
long-lived process that re-opens, re-maps and re-hashes the same files every
round (bench/daemon.bend, bench/rust/src/bin/daemon.rs); the first rounds
are warm-up and dropped. Processes alternate, three times each, so drift on
a busy machine hits all sides alike. Folds (XOR of all hash words) must
agree.

usage: bench/daemon.py [rounds] [workload ...]   (workloads as bench/race.py)
"""

import os
import pathlib
import statistics
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from race import WORKLOADS  # noqa: E402

RUST = HERE / "rust" / "target" / "release" / "daemon"
BEND = HERE / "build" / "daemon"
SIDES = {
    "rust seq (b3sum)": lambda r, a: [str(RUST), str(r), "seq"] + a,
    "rust par (rayon)": lambda r, a: [str(RUST), str(r), "par"] + a,
    "bend": lambda r, a: [str(BEND), str(r)] + a,
}
WARM = 2


def rounds_of(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    rows = [line.split() for line in out.splitlines() if line.startswith("us ")]
    return [float(r[1]) / 1000 for r in rows], {r[3] for r in rows}


def race(name, args, rounds):
    times = {k: [] for k in SIDES}
    folds = set()
    for _ in range(3):
        for k, cmd in SIDES.items():
            t, f = rounds_of(cmd(rounds + WARM, args))
            times[k] += t[WARM:]
            folds |= f
    if len(folds) != 1:
        sys.exit(f"{name}: folds differ: {folds}")
    med = {k: statistics.median(v) for k, v in times.items()}
    best = med["rust par (rayon)"]
    cells = " | ".join(f"{med[k]:8.1f}" for k in SIDES)
    ratio = best / med["bend"]
    verdict = f"{ratio:.2f}x faster" if ratio >= 1 else f"{1 / ratio:.2f}x slower"
    print(f"| {name:<14} | {cells} | bend vs rayon: {verdict} |", flush=True)


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    names = sys.argv[2:] or [n for n in WORKLOADS if n != "5 GiB file"]
    print(f"daemon rounds: {rounds} per process x 3 (after {WARM} warm-up), "
          f"median ms per round (load avg {os.getloadavg()[0]:.1f})\n")
    print("| workload       | " + " | ".join(f"{k:>8}" for k in SIDES) + " | result |")
    print("|----------------|" + "|".join("-" * 10 for _ in SIDES) + "|--------|")
    for n in names:
        race(n, WORKLOADS[n](), rounds)


if __name__ == "__main__":
    main()
