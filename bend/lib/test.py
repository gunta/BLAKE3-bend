#!/usr/bin/env python3
"""libturboblake against the official test vectors and the official b3sum.

Runs build/bin/blake3 (cli.c over blake3.h) on every case of
test_vectors/test_vectors.json in all three modes, with extended output and
a seek, under several update splits, with TURBOBLAKE_MIN=2048 so that the
engine hashes every subtree of two chunks or more. Then hashes random inputs
around the engine's edges (up to 2 GiB + 1 with --big) against b3sum.
    python3 bend/lib/test.py [--big]
"""
import json
import os
import pathlib
import random
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLI = HERE / "build" / "bin" / "blake3"
B3SUM = ROOT / "b3sum" / "target" / "release" / "b3sum"
VECTORS = json.loads((ROOT / "test_vectors" / "test_vectors.json").read_text())
ENV = {**os.environ, "TURBOBLAKE_MIN": "2048"}


def pattern(n):
    return bytes(i % 251 for i in range(n))


def run(args, data, env=ENV):
    return subprocess.run([str(CLI)] + args, input=data, capture_output=True, env=env,
                          check=True).stdout.decode().strip()


def main():
    key = VECTORS["key"].encode().hex()
    ctx = VECTORS["context_string"]
    bad = checks = 0
    for case in VECTORS["cases"]:
        n = case["input_len"]
        data = pattern(n)
        for mode, args in (("hash", []), ("keyed_hash", ["--keyed", key]),
                           ("derive_key", ["--derive-key", ctx])):
            want = case[mode]
            for split in ([0, 1, 63, 1024, 1025, 3000, 8192] if n > 1024 else [0, 1]):
                s = ["--split", str(split)] if split else []
                for extra, exp in ((["--length", "32"], want[:64]),
                                   (["--length", str(len(want) // 2)], want),
                                   (["--length", "32", "--seek", "7"], want[14:78])):
                    got = run(args + s + extra, data)
                    checks += 1
                    if got != exp:
                        bad += 1
                        print(f"MISMATCH {mode} len={n} split={split} {extra}\n  got  {got}\n  want {exp}")
    print(f"{checks - bad}/{checks} official vector checks pass")

    sizes = [2048, 2049, 4096 + 1, 65536, 262144 - 1, 262144, 262144 + 1, (1 << 20) * 3 + 77,
             (1 << 20) * 3 + 64, (16 << 20) + 1024, 64 << 20]
    if "--big" in sys.argv:
        sizes += [(1 << 30) - 1024, 1 << 30, (1 << 30) + 1, (1 << 30) + 1024 * 5 + 64,
                  (2 << 30) + 1, (3 << 30) + 7]
    rnd = random.Random(7)
    for n in sizes:
        data = b"".join(rnd.randbytes(min(n - i, 1 << 24)) for i in range(0, n, 1 << 24))
        want = subprocess.run([str(B3SUM), "--no-names", "-"], input=data, capture_output=True,
                              check=True).stdout.decode().strip()
        for split, env in ((0, ENV), (0, os.environ), (1 << 20, ENV), (1000, ENV), (-1, ENV)):
            args = ["--whole"] if split < 0 else ["--split", str(split)] if split else []
            got = run(args, data, env)
            checks += 1
            if got != want:
                bad += 1
                print(f"MISMATCH random len={n} split={split} min={env.get('TURBOBLAKE_MIN')}\n"
                      f"  got  {got}\n  want {want}")
    print(f"{checks - bad}/{checks} checks pass in all" + ("" if bad else ": libturboblake matches"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
