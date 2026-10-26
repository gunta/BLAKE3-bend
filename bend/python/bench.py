#!/usr/bin/env python3
"""Python: turboblake against the blake3 module on PyPI, and hashlib.

The two blake3 modules share a name, so each runs in its own interpreter:

    python3 bench.py race --bend <python with turboblake> --pypi <python with blake3>

prints a table and writes bench/results/lang-python.json. A worker
(`bench.py worker <label> [--others]`) times one-shot `blake3(data).digest()`
(and, for the PyPI module, also with max_threads=blake3.AUTO; turboblake
ignores max_threads), plus hashlib's hashes with --others, and prints one
JSON line per (implementation, size): the median of interleaved runs and
the digest of the first.
"""
import hashlib
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

SIZES = [1 << 10, 64 << 10, 1 << 20, 16 << 20, 256 << 20, 1 << 30]
OTHERS = ["sha256", "sha512", "sha1", "md5", "blake2b", "blake2s", "sha3_256"]
HERE = pathlib.Path(__file__).resolve().parent


def reps_for(n):
    return 30 if n <= 1 << 20 else 10 if n <= 64 << 20 else 5


def worker(label, others):
    # the installed module, not the source package beside this script
    sys.path[:] = [p for p in sys.path if pathlib.Path(p or ".").resolve() != HERE]
    import blake3

    data = bytes((i * 2654435761 >> 13) & 255 for i in range(1 << 16)) * ((1 << 30) // (1 << 16))
    view = memoryview(data)
    sides = {label: lambda b: blake3.blake3(b).digest()}
    if label == "blake3 (PyPI)":
        sides["blake3 (PyPI), max_threads=AUTO"] = lambda b: blake3.blake3(
            b, max_threads=blake3.blake3.AUTO).digest()
    if others:
        for name in OTHERS:
            sides[f"hashlib.{name}"] = (lambda nm: lambda b: hashlib.new(nm, b).digest())(name)
    for n in SIZES:
        b = view[:n]
        times = {k: [] for k in sides}
        digest = {k: f(b).hex() for k, f in sides.items()}
        for _ in range(reps_for(n)):
            for k, f in sides.items():
                t = time.perf_counter()
                f(b)
                times[k].append((time.perf_counter() - t) * 1000)
        for k in sides:
            print(json.dumps({"impl": k, "bytes": n, "ms": statistics.median(times[k]),
                              "digest": digest[k][:16]}), flush=True)


def race(bend, pypi):
    rows = []
    for py, label, others in ((pypi, "blake3 (PyPI)", False), (bend, "turboblake", True)):
        out = subprocess.run([py, str(HERE / "bench.py"), "worker", label] + (["--others"] if others else []),
                             capture_output=True, text=True, check=True).stdout
        rows += [json.loads(line) for line in out.splitlines()]
    impls = list(dict.fromkeys(r["impl"] for r in rows))
    by = {(r["impl"], r["bytes"]): r for r in rows}
    agree = all(by[("blake3 (PyPI)", n)]["digest"] == by[("turboblake", n)]["digest"] for n in SIZES)
    print("| bytes | " + " | ".join(impls) + " |")
    print("|---:|" + "---:|" * len(impls))
    for n in SIZES:
        size = f"{n >> 30} GiB" if n >= 1 << 30 else f"{n >> 20} MiB" if n >= 1 << 20 else f"{n >> 10} KiB"
        print(f"| {size} | " + " | ".join(f"{by[(k, n)]['ms']:.3f} ms" for k in impls) + " |")
    print(f"\nblake3 digests {'agree' if agree else 'DIFFER'}")
    info = {"python": subprocess.run([bend, "-c", "import sys; print(sys.version.split()[0])"],
                                     capture_output=True, text=True).stdout.strip(),
            "load_avg": os.getloadavg()[0], "digests_agree": agree}
    out = HERE.parents[0] / "bench" / "results" / "lang-python.json"
    out.write_text(json.dumps({"info": info, "rows": rows}, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    if sys.argv[1] == "worker":
        worker(sys.argv[2], "--others" in sys.argv)
    else:
        args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
        race(args["--bend"], args["--pypi"])
