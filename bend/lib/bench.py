#!/usr/bin/env python3
"""libblake3-bend against the official C library, through the same blake3.h.

Builds bench.c twice: against build/lib/libblake3.a (the hook and the Bend
engine) and against the official c/ sources compiled the same way (SIMD,
one thread: the C library has no threads of its own without TBB). Hashes
one in-memory buffer per size; prints medians and checks the digests.
    python3 bend/lib/bench.py [reps]
"""
import json
import os
import pathlib
import platform
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "build" / "bench"
SIZES = [1 << 10, 16 << 10, 64 << 10, 256 << 10, 1 << 20, 4 << 20, 16 << 20, 64 << 20,
         256 << 20, 1 << 30]


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    cc = os.environ.get("CC", "clang")
    arm = platform.machine() in ("arm64", "aarch64")
    cpu = "-mcpu=native" if arm else "-march=native"
    srcs = ["blake3.c", "blake3_dispatch.c", "blake3_portable.c"]
    if arm:
        srcs += ["blake3_neon.c"]
    else:
        srcs += [f"blake3_{s}_x86-64_unix.S" for s in ("sse2", "sse41", "avx2", "avx512")]
    flags = ["-O3", cpu] + (["-DBLAKE3_USE_NEON=1"] if arm else [])
    subprocess.run([cc, *flags, "-I", str(ROOT / "c"), str(HERE / "bench.c"),
                    *[str(ROOT / "c" / s) for s in srcs], "-o", str(OUT / "official")], check=True)
    subprocess.run([cc, "-O3", cpu, "-I", str(HERE / "build" / "include"), str(HERE / "bench.c"),
                    str(HERE / "build" / "lib" / "libblake3.a"), "-lpthread", "-lm",
                    "-o", str(OUT / "bend")], check=True)


def run(exe, n, reps):
    out = subprocess.run([str(OUT / exe), str(n), str(reps)], capture_output=True, text=True,
                         check=True).stdout.split()
    return float(out[1]), out[-1]


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    build()
    print("| bytes | official C (1 thread, SIMD) | libblake3-bend | | digest |")
    print("|---:|---:|---:|---:|:---:|")
    rows, agree = [], True
    for n in SIZES:
        r = max(3, reps if n <= 64 << 20 else reps // 3)
        a, da = run("official", n, r)
        b, db = run("bend", n, r)
        agree = agree and da == db
        rows += [{"impl": "official C", "bytes": n, "ms": a / 1000, "digest": da[:16]},
                 {"impl": "libblake3-bend", "bytes": n, "ms": b / 1000, "digest": db[:16]}]
        size = f"{n >> 30} GiB" if n >= 1 << 30 else f"{n >> 20} MiB" if n >= 1 << 20 else f"{n >> 10} KiB"
        print(f"| {size} | {a / 1000:.3f} ms | {b / 1000:.3f} ms | {a / b:.2f}x | "
              f"{'ok' if da == db else 'DIFFER'} |", flush=True)
    out = ROOT / "bend" / "bench" / "results" / f"lang-c{'-' + platform.system().lower() if platform.system() != 'Darwin' else ''}.json"
    out.write_text(json.dumps({"info": {"machine": platform.machine(), "system": platform.system(),
                                        "digests_agree": agree}, "rows": rows}, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
