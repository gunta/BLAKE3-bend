"""Bend2 BLAKE3 on NVIDIA GPUs, on Modal (https://modal.com/docs/guide/gpu).

Builds bench/mem.bend for Linux + CUDA on a Modal GPU box and times the GPU
path (`hash1!`) from 64 MiB to 2 GiB in memory, the CPU path (8-lane
compress8), and the official blake3 crate (SIMD + rayon) on the same host's
CPUs, checking that every digest agrees. Writes
bend/bench/results/modal-<gpu>.json and prints a table.

This costs money (GPU time is billed by the second): run it on purpose.

    modal run bend/bench/modal_gpu.py --gpu L4            # cheapest smoke test
    modal run bend/bench/modal_gpu.py --gpu H100!         # exactly an H100
    modal run bend/bench/modal_gpu.py --gpu B200 --max-log 29

`--max-log d` hashes up to 4 * 2^d bytes (29: 2 GiB; mem.bend's length is a
U32, so 29 is the top).
"""

import json
import os
import pathlib
import re
import statistics
import subprocess
import time

import modal

# The repository on the machine running `modal run`; inside the container
# this file is /root/modal_gpu.py and the repository is mounted at /repo.
_HERE = pathlib.Path(__file__).resolve()
REPO = _HERE.parents[2] if modal.is_local() else pathlib.Path("/repo")
CUDA_IMAGE = os.environ.get("BEND_CUDA_IMAGE", "nvidia/cuda:13.4.3-devel-ubuntu24.04")
LLVM = 20
# The CPU flags of bend/build.sh (ADR 0002), with -march=native for x86.
TUNE = ("-O3 -march=native -mllvm -slp-max-reg-size=512 "
        "-mllvm -slp-recursion-max-depth=100000 -mllvm -slp-threshold=-20 "
        "-mllvm -inline-threshold=20000")

image = (
    modal.Image.from_registry(CUDA_IMAGE, add_python="3.12")
    .apt_install("curl", "ca-certificates", "wget", "gnupg", "lsb-release",
                 "software-properties-common", "build-essential", "git", "pciutils")
    .run_commands(
        f"wget -qO /tmp/llvm.sh https://apt.llvm.org/llvm.sh && bash /tmp/llvm.sh {LLVM}",
        "curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal",
        "curl -fsSL https://bend-lang.com/install.sh | BEND_NO_TELEMETRY=1 sh",
    )
    .env({
        "PATH": f"/root/.bend/bin:/root/.cargo/bin:/usr/lib/llvm-{LLVM}/bin:"
                "/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "CUDA_HOME": "/usr/local/cuda",
        "BEND_NO_TELEMETRY": "1",
        # compress8 is one def of ~3600 lets: the checker needs a deep stack
        "JSC_maxPerThreadStackUsage": "60000000",
        "BUN_JSC_maxPerThreadStackUsage": "60000000",
    })
    .add_local_dir(REPO, "/repo", ignore=[
        ".git", "**/target", "**/build", "bend/bench/data", "site/node_modules",
        "site/dist", "media", "**/.DS_Store",
    ])
)

app = modal.App("blake3-bend-gpu", image=image)


def sh(cmd, cwd=None, env=None):
    t = time.time()
    r = subprocess.run(["bash", "-lc", f"ulimit -s 65520 2>/dev/null; {cmd}"], cwd=cwd,
                       env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"`{cmd}` failed ({r.returncode}):\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")
    print(f"[{time.time() - t:6.1f}s] {cmd}", flush=True)
    return r.stdout


def runs(out):
    """`us <micros> bytes <n> <hex>` lines -> (times in ms, digests)."""
    rows = [line.split() for line in out.splitlines() if line.startswith("us ")]
    return [int(r[1]) / 1000 for r in rows], {r[-1] for r in rows}


def summary(ms, skip=1):
    rest = ms[skip:] or ms
    return {"runs_ms": ms, "min_ms": min(rest), "median_ms": statistics.median(rest)}


@app.function(gpu="L4", cpu=16, memory=65536, timeout=3600)
def bench(max_log: int = 28, reps: int = 6) -> dict:
    work = "/work"
    sh(f"rm -rf {work} && cp -r /repo {work}")
    bend = f"{work}/bend"
    info = {
        "gpu": sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader").strip(),
        "cpu": sh("lscpu | sed -n 's/^Model name:[ ]*//p'").strip(),
        "cpus": int(sh("nproc").strip()),
        "bend": sh("bend version").strip(),
        "cuda": sh("nvcc --version | tail -2 | head -1").strip(),
        "clang": sh("clang --version | head -1").strip(),
    }
    print(info, flush=True)

    # bend's own Linux + CUDA build, with the tuned CPU flags added to its
    # clang call by a shim first on PATH.
    sh("mkdir -p /tmp/shim && printf '#!/bin/sh\\nexec /usr/lib/llvm-%d/bin/clang \"$@\" $BEND_TUNE\\n' "
       f"{LLVM} > /tmp/shim/clang && chmod +x /tmp/shim/clang && cp /tmp/shim/clang /tmp/shim/cc")
    shim = {"PATH": "/tmp/shim:" + os.environ["PATH"], "BEND_TUNE": TUNE}
    sh("mkdir -p bench/build && python3 tools/gen_blake3.py", cwd=bend)
    sh("bend bench/mem.bend -o bench/build/mem", cwd=bend, env=shim)
    sh("RUSTFLAGS='-C target-cpu=native' cargo build --release --quiet", cwd=f"{bend}/bench/rust")
    mem = f"{bend}/bench/build/mem"
    ref = f"{bend}/bench/rust/target/release/b3ref"

    rows = []
    for d in range(24, max_log + 1):
        size = 4 << d
        heap = max(4, 3 * (size >> 30) + 2)
        g_ms, g_dig = runs(sh(f"{mem} +RTS --gpu {heap}GB -RTS {d} {reps} 1"))
        c_ms, c_dig = runs(sh(f"{mem} +RTS --gpu off -RTS {d} {reps} 0"))
        r_ms, r_dig = runs(sh(f"{ref} {d} {reps} 0"))
        digests = g_dig | c_dig | r_dig
        row = {
            "bytes": size,
            "bend_gpu": summary(g_ms),
            "bend_cpu": summary(c_ms),
            "rust_cpu": summary(r_ms),
            "digest": sorted(digests)[0],
            "digests_agree": len(digests) == 1,
        }
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("bytes", "digests_agree")}),
              {k: row[k]["min_ms"] for k in ("bend_gpu", "bend_cpu", "rust_cpu")}, flush=True)
    one = 28 if max_log >= 28 else max_log
    single = {
        "bytes": 4 << one,
        "bend_cpu_1t": summary(runs(sh(f"{mem} +RTS --gpu off --threads 1 -RTS {one} 3 0"))[0]),
        "rust_cpu_1t": summary(runs(sh(f"{ref} {one} 3 2"))[0]),
    }
    return {"info": info, "rows": rows, "single_thread": single,
            "note": "warm, in memory; min/median skip the first run (CUDA managed "
                    "memory moves the pages to the GPU on first touch)"}


# Managed memory, the way Bend's CUDA runtime uses it: the host writes, a
# kernel reads and writes, the host reads after a sync.
MANAGED = r"""
#include <cuda_runtime.h>
#include <stdio.h>
__global__ void bump(volatile int* p) { p[1] = p[0] + 1; }
int main() {
  int concurrent = 0;
  cudaDeviceGetAttribute(&concurrent, cudaDevAttrConcurrentManagedAccess, 0);
  int* p; cudaMallocManaged(&p, 2 * sizeof(int), cudaMemAttachGlobal);
  p[0] = 41; p[1] = 0;
  bump<<<1, 1>>>(p);
  cudaError_t e = cudaDeviceSynchronize();
  printf("concurrentManagedAccess=%d sync=%s host reads %d (want 42)\n", concurrent,
         cudaGetErrorString(e), p[1]);
  return p[1] == 42 ? 0 : 1;
}
"""

POW2 = """import Base

def pow2(+n: Nat) -> U32:
  match n:
    case 0n:
      1
    case 1n+p:
      a b = pow2(p) pow2(p)
      (a + b : U32)

def main() -> IO(Unit):
  IO.print(U32.show(pow2!(20n)))
"""


@app.function(gpu="L4", cpu=8, memory=32768, timeout=1200)
def debug() -> str:
    """Small GPU steps, each under a timeout, to find where a run hangs."""
    log = []

    def step(name, cmd, cwd="/work/bend", env=None, limit=120):
        t = time.time()
        try:
            r = subprocess.run(["bash", "-lc", f"ulimit -s 65520 2>/dev/null; {cmd}"], cwd=cwd,
                               env={**os.environ, **(env or {})}, capture_output=True,
                               text=True, timeout=limit)
            out = f"exit {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
        except subprocess.TimeoutExpired as e:
            out = f"TIMEOUT after {limit}s\n{(e.stdout or b'')[-1500:]!r}\n{(e.stderr or b'')[-1500:]!r}"
        log.append(f"== {name} ({time.time() - t:.1f}s)\n{out}")
        print(log[-1], flush=True)
        return out.startswith("exit 0")

    subprocess.run("rm -rf /work && cp -r /repo /work && mkdir -p /work/bend/bench/build",
                   shell=True, check=True)
    pathlib.Path("/work/pow2.bend").write_text(POW2)
    pathlib.Path("/work/managed.cu").write_text(MANAGED)
    step("CUDA managed memory", "nvcc -O2 managed.cu -o managed && ./managed", cwd="/work", limit=60)
    step("pow2! plain build", "bend pow2.bend -o pow2 && ls -la pow2*", cwd="/work")
    step("nvidia-smi", "nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv", cwd="/work")
    ok = step("pow2! run", "./pow2", cwd="/work", limit=45)
    step("pow2 on CPU", "./pow2 +RTS --gpu off -RTS", cwd="/work", limit=60)
    if not ok:
        return "\n".join(log)
    step("mem plain build", "python3 tools/gen_blake3.py && bend bench/mem.bend -o bench/build/mem_plain")
    step("mem plain cpu d=16", "bench/build/mem_plain +RTS --gpu off -RTS 16 2 0", limit=60)
    step("mem plain gpu d=16", "bench/build/mem_plain 16 2 1", limit=120)
    step("mem plain gpu d=20 4GB", "bench/build/mem_plain +RTS --gpu 4GB -RTS 20 2 1", limit=120)
    return "\n".join(log)


@app.local_entrypoint()
def main(gpu: str = "L4", max_log: int = 28, reps: int = 6, debug_only: bool = False):
    if debug_only:
        print(debug.with_options(gpu=gpu).remote())
        return
    t = time.time()
    res = bench.with_options(gpu=gpu).remote(max_log, reps)
    res["requested_gpu"] = gpu
    res["wall_s"] = round(time.time() - t, 1)
    out = REPO / "bend" / "bench" / "results" / f"modal-{re.sub(r'[^A-Za-z0-9.-]+', '_', gpu)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    i = res["info"]
    print(f"\n{i['gpu']} | {i['cpu']} x{i['cpus']} | {i['bend']}")
    print("| bytes | Bend GPU | Bend CPU | Rust blake3 CPU | GPU vs Rust | digests |")
    print("|------:|---------:|---------:|----------------:|------------:|:-------:|")
    for r in res["rows"]:
        g, c, rr = r["bend_gpu"]["min_ms"], r["bend_cpu"]["min_ms"], r["rust_cpu"]["min_ms"]
        print(f"| {r['bytes'] >> 20} MiB | {g:.2f} ms | {c:.2f} ms | {rr:.2f} ms | "
              f"{rr / g:.2f}x | {'ok' if r['digests_agree'] else 'DIFFER'} |")
    s = res["single_thread"]
    print(f"\n1 thread, {s['bytes'] >> 20} MiB: Bend {s['bend_cpu_1t']['min_ms']:.1f} ms, "
          f"Rust {s['rust_cpu_1t']['min_ms']:.1f} ms")
    print(f"wrote {out} ({res['wall_s']} s)")
