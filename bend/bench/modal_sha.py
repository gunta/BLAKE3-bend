"""SHA-256 and the official BLAKE3 on the CPU of a Modal GPU host.

modal_gpu.py times BLAKE3 on the GPU and on the host's cores; this adds
what most people hash with today, on the same kind of machine: SHA-256
through OpenSSL (Python's hashlib, with the CPU's SHA extensions where it
has them), and the official BLAKE3 crate (PyPI's blake3) on one thread and
on every core, over the same in-memory buffer. SHA-256 chains each block to
the one before, so one input runs on one core whatever the machine has.
Writes bend/bench/results/modal-sha-<gpu>.json.

This costs money (GPU time is billed by the second): run it on purpose.

    modal run bend/bench/modal_sha.py --gpu B200
"""

import hashlib
import json
import os
import pathlib
import platform
import ssl
import statistics
import subprocess
import time

import modal

image = modal.Image.debian_slim(python_version="3.12").pip_install("blake3")
app = modal.App("turboblake-sha", image=image)

SIZES = [1 << 30, 2 << 30]


def timed(f, reps):
    """ms of each run and the digest, the first run (paging the buffer in) left out."""
    ms, digest = [], None
    for _ in range(reps + 1):
        t = time.perf_counter()
        digest = f()
        ms.append((time.perf_counter() - t) * 1e3)
    rest = ms[1:]
    return {"runs_ms": [round(x, 3) for x in ms], "min_ms": round(min(rest), 3),
            "median_ms": round(statistics.median(rest), 3), "digest": digest}


def cpu_info():
    text = pathlib.Path("/proc/cpuinfo").read_text()
    model = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.startswith("model name")), "unknown")
    flags = next((l.split(":", 1)[1].split() for l in text.splitlines() if l.startswith("flags")), [])
    return model, "sha_ni" in flags, "avx512f" in flags


@app.function(gpu="B200", cpu=16, memory=16384, timeout=900)
def sha(reps: int = 5) -> dict:
    import blake3

    model, sha_ni, avx512 = cpu_info()
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                              "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        gpu = "unknown"
    info = {"gpu": gpu, "cpu": model, "cpus": os.cpu_count(), "sha_ni": sha_ni, "avx512f": avx512,
            "python": platform.python_version(), "openssl": ssl.OPENSSL_VERSION, "blake3": blake3.__version__}
    print(info, flush=True)
    rows = []
    for n in SIZES:
        buf = bytes(range(251)) * (n // 251) + bytes(n % 251)
        row = {
            "bytes": n,
            "sha256": timed(lambda: hashlib.sha256(buf).hexdigest(), reps),
            "blake3_1t": timed(lambda: blake3.blake3(buf).hexdigest(), reps),
            "blake3_all": timed(lambda: blake3.blake3(buf, max_threads=blake3.blake3.AUTO).hexdigest(), reps),
        }
        row["blake3_agree"] = row["blake3_1t"]["digest"] == row["blake3_all"]["digest"]
        rows.append(row)
        print(n, {k: v["median_ms"] for k, v in row.items() if isinstance(v, dict)}, flush=True)
        del buf
    return {"info": info, "rows": rows,
            "note": "in memory, one buffer per size; medians, the first run (paging the buffer in) left out"}


@app.local_entrypoint()
def main(gpu: str = "B200", reps: int = 5):
    out = sha.with_options(gpu=gpu).remote(reps)
    out["requested_gpu"] = gpu
    path = pathlib.Path(__file__).resolve().parent / "results" / f"modal-sha-{gpu.rstrip('!')}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {path}")
    for r in out["rows"]:
        print(f"{r['bytes'] >> 20:>6} MiB  " + "  ".join(
            f"{k} {v['median_ms']:.1f} ms ({r['bytes'] / v['median_ms'] / 1e6:.2f} GB/s)"
            for k, v in r.items() if isinstance(v, dict)))
