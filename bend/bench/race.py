#!/usr/bin/env python3
"""End-to-end race: official b3sum vs the Bend b3sums, file workloads.

Runs every command of a workload once per round, in an order that flips each
round, so drift on a busy machine hits every side alike; reports the median
and the minimum wall time. Checks that all print the same bytes first.

usage: bench/race.py [rounds] [workload ...]
B3RACE_SIDES=name=path,... picks the sides (the first is the baseline);
the default is the official b3sum and bend/build/b3sum (bend/b3sum.bend),
plus b3bend (bend/crate: the official b3sum with the engine) when built.
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
RUST = ROOT / "bend" / "crate" / "target" / "release" / "b3bend"


def sides_of():
    spec = os.environ.get("B3RACE_SIDES")
    if spec:
        return dict(kv.split("=", 1) for kv in spec.split(","))
    sides = {"b3sum": str(REF), "bend": str(BEND)}
    if RUST.exists():
        sides["b3bend"] = str(RUST)
    return sides


def files(pattern):
    return sorted(str(p) for p in DATA.glob(pattern))


def tree(root, limit=None):
    out = []
    for dirpath, _, names in os.walk(os.path.expanduser(root)):
        out += [os.path.join(dirpath, n) for n in sorted(names)]
    out = sorted(p for p in out if os.path.isfile(p) and not os.path.islink(p))
    return out[:limit] if limit else out


SDK = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/usr/include"

WORKLOADS = {
    "1 GiB file": lambda: [str(DATA / "big_1g.bin")],
    "64 MiB file": lambda: [str(DATA / "mid_64m.bin")],
    "10k x 4 KiB": lambda: files("small4k/*"),
    "2k x 64 KiB": lambda: files("small64k/*"),
    "1k x 1 MiB": lambda: files("med1m/*"),
    "SDK headers": lambda: tree(SDK),
    "cargo src 8k": lambda: tree("~/.cargo/registry/src", 8000),
    "5 GiB file": lambda: [str(DATA / "huge_5g.bin")],
    # deepseek-ai/DeepSeek-V4.1-Flash-1017 (MIT), via bench/hf_fetch.py
    "DeepSeek shards 1-6": lambda: files("hf/DeepSeek-V4.1-Flash-1017/model-0000[1-6]-of-00048.safetensors"),
    "DeepSeek 101 GB shard": lambda: [str(DATA / "hf/DeepSeek-V4.1-Flash-1017/model-00048-of-00048.safetensors")],
}


def run(cmd):
    t = time.perf_counter()
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return (time.perf_counter() - t) * 1000


def race(name, args, rounds, bins):
    sides = {k: [b] + args for k, b in bins.items()}
    outs = {k: subprocess.run(v, capture_output=True).stdout for k, v in sides.items()}
    base = next(iter(sides))
    for k in sides:
        if outs[k] != outs[base]:
            sys.exit(f"{name}: {k}'s output differs from {base}'s")
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
    cells = " | ".join(f"{med[k]:8.1f} | {lo[k]:8.1f}" for k in sides)
    verdicts = []
    for k in list(sides)[1:]:
        ratio = med[base] / med[k]
        verdicts.append(f"{k} {ratio:.2f}x faster" if ratio >= 1 else f"{k} {1 / ratio:.2f}x slower")
    print(f"| {name:<12} | {cells} | {'; '.join(verdicts)} |", flush=True)


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    names = sys.argv[2:] or [n for n in WORKLOADS if n != "5 GiB file"]
    bins = sides_of()
    print(f"{rounds} interleaved rounds, wall ms "
          f"(load avg {os.getloadavg()[0]:.1f})\n")
    head = " | ".join(f"{k} md | {k} lo" for k in bins)
    print(f"| workload     | {head} | result |")
    print("|--------------|" + "----------|----------|" * len(bins) + "--------|")
    for n in names:
        race(n, WORKLOADS[n](), rounds, bins)


if __name__ == "__main__":
    main()
