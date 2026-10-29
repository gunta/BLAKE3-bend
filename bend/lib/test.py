#!/usr/bin/env python3
"""libturboblake against the official test vectors and the official b3sum.

Runs build/bin/blake3 (cli.c over blake3.h) on every case of
test_vectors/test_vectors.json in all three modes, with extended output and
a seek, under several update splits, with TURBOBLAKE_MIN=2048 so that the
engine hashes every subtree of two chunks or more. Then hashes random inputs
around the engine's edges (up to 2 GiB + 1 with --big) against b3sum.

With a GPU backend (ADR 0017) the same checks run through the GPU too:
the input in GPU memory (--gpu: a private Metal buffer or CUDA device
memory, at an odd offset, updates alternating with host ones), in a shared
Metal buffer, in turboblake_alloc's memory (split with the engine), and host
memory under TURBOBLAKE_GPU=all (the GPU takes every subtree, alone or split
with the engine), with TURBOBLAKE_GPU_MIN=2048.
    python3 bend/lib/test.py [--big] [--cli PATH]   (B3SUM=PATH: the official b3sum)
"""
import json
import os
import pathlib
import random
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLI = pathlib.Path(sys.argv[sys.argv.index("--cli") + 1]) if "--cli" in sys.argv else \
    HERE / "build" / "bin" / "blake3"
B3SUM = os.environ.get("B3SUM") or ROOT / "b3sum" / "target" / "release" / "b3sum"
VECTORS = json.loads((ROOT / "test_vectors" / "test_vectors.json").read_text())
ENV = {**os.environ, "TURBOBLAKE_MIN": "2048"}
GPU_ENV = {**ENV, "TURBOBLAKE_GPU_MIN": "2048"}
ALL_ENV = {**GPU_ENV, "TURBOBLAKE_GPU": "all"}
HALF_ENV = {**ALL_ENV, "TURBOBLAKE_GPU_SHARE": "0.5"}


def pattern(n):
    return bytes(i % 251 for i in range(n))


def run(args, data, env=ENV):
    return subprocess.run([str(CLI)] + args, input=data, capture_output=True, env=env,
                          check=True).stdout.decode().strip()


def vectors(label, base, env, splits):
    """Every official case in all three modes, with extended output and a
    seek, under the update splits: (checks, mismatches)."""
    key = VECTORS["key"].encode().hex()
    ctx = VECTORS["context_string"]
    bad = checks = 0
    for case in VECTORS["cases"]:
        n = case["input_len"]
        data = pattern(n)
        for mode, args in (("hash", []), ("keyed_hash", ["--keyed", key]),
                           ("derive_key", ["--derive-key", ctx])):
            want = case[mode]
            for split in (splits if n > 1024 else [0, 1]):
                s = ["--split", str(split)] if split else []
                for extra, exp in ((["--length", "32"], want[:64]),
                                   (["--length", str(len(want) // 2)], want),
                                   (["--length", "32", "--seek", "7"], want[14:78])):
                    got = run(base + args + s + extra, data, env)
                    checks += 1
                    if got != exp:
                        bad += 1
                        print(f"MISMATCH {label} {mode} len={n} split={split} {extra}\n"
                              f"  got  {got}\n  want {exp}")
    print(f"{checks - bad}/{checks} official vector checks pass ({label})")
    return checks, bad


def main():
    checks, bad = vectors("CPU", [], ENV, [0, 1, 63, 1024, 1025, 3000, 8192])
    gpu = run(["--gpu-info"], b"")
    if gpu != "none":
        # the GPU paths: device memory (private, odd offset, alternating with
        # host updates), a shared Metal buffer, and host memory through the hook
        passes = [("GPU memory", ["--gpu", "--offset", "5", "--mix"], GPU_ENV,
                   [0, 1, 63, 1025, 3000, 8192]),
                  ("host memory, TURBOBLAKE_GPU=all", [], ALL_ENV, [0, 1025, 8192]),
                  ("host memory, split with the engine", [], HALF_ENV, [0, 3000])]
        if gpu == "metal":
            passes.insert(1, ("shared Metal buffer", ["--gpu", "shared", "--offset", "16"], GPU_ENV,
                              [0, 1, 1024, 8192]))
        for label, base, env, splits in passes:
            c, b = vectors(f"{gpu}: {label}", base, env, splits)
            checks += c
            bad += b

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
        cases = [([], ENV), ([], os.environ), (["--split", str(1 << 20)], ENV),
                 (["--split", "1000"], ENV), (["--whole"], ENV)]
        if gpu != "none":
            cases += [(["--gpu"], GPU_ENV), (["--gpu", "--offset", "5", "--split", "1000", "--mix"], GPU_ENV),
                      (["--gpu", "--split", str((3 << 20) + 1024)], os.environ),
                      ([], ALL_ENV), ([], HALF_ENV), (["--whole"], HALF_ENV),
                      (["--alloc"], GPU_ENV), (["--alloc", "--split", str(1 << 20)], os.environ),
                      (["--alloc"], {**GPU_ENV, "TURBOBLAKE_GPU_SHARE": "0.5"})]
            if gpu == "metal":
                cases += [(["--gpu", "shared", "--offset", "4096"], GPU_ENV),
                          (["--gpu", "shared", "--split", str(1 << 20)], {**os.environ, "TURBOBLAKE_GPU_SHARE": "0.5"})]
        for args, env in cases:
            got = run(args, data, env)
            checks += 1
            if got != want:
                bad += 1
                gpu_env = {k: v for k, v in env.items() if k.startswith("TURBOBLAKE")}
                print(f"MISMATCH random len={n} {' '.join(args)} {gpu_env}\n"
                      f"  got  {got}\n  want {want}")
    print(f"{checks - bad}/{checks} checks pass in all" + ("" if bad else ": libturboblake matches"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
