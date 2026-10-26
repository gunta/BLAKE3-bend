"""Bend2 BLAKE3 on NVIDIA GPUs, on Modal (https://modal.com/docs/guide/gpu).

Builds bench/mem.bend for Linux + CUDA on a Modal GPU box and times the GPU
path (`hash1!`) from 64 MiB to 2 GiB in memory against the hand-written
CUDA reference (bend/ref/cuda), the CPU path (8-lane compress8), and the
official blake3 crate (SIMD + rayon) on the same host's CPUs, checking that
every digest agrees. Writes
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
                 "software-properties-common", "build-essential", "git", "pciutils", "gdb")
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
        "site/dist", "media", "**/.DS_Store", ".claude", "**/node_modules",
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


SIDES = ("bend_gpu", "native_cuda", "native_cuda_bend_shape", "bend_cpu", "rust_cpu")


def summary(ms, skip=1):
    rest = ms[skip:] or ms
    return {"runs_ms": ms, "min_ms": min(rest), "median_ms": statistics.median(rest)}


# Modal runs containers under gVisor, whose CUDA proxy hangs on any managed
# allocation past 1 GiB (plain CUDA too: see debug_advise). Bend's CUDA
# runtime maps its whole heap with one cuMemAllocManaged, so the shim swaps
# its gpu_map for one that asks for 1 GiB at a time and checks that each
# lands next to the ones before (the driver places them back to back). Only
# the host's allocation changes; the device program, and so the .gpu cache
# key, is Bend's own.
CHUNKED = r"""
import re, sys
p = sys.argv[1]
s = open(p).read()
new = '''static u64* gpu_map(u64 bytes) {
  const u64 G = 1ull << 30;
  CUdeviceptr lo = 0, hi = 0;
  for (u64 at = 0; at < bytes; at += G) {
    CUdeviceptr q = 0;
    CUresult r = cuMemAllocManaged(&q, G, CU_MEM_ATTACH_GLOBAL);
    if (r == CUDA_SUCCESS && at == 0) {
      lo = q, hi = q + G;
    } else if (r == CUDA_SUCCESS && q == hi) {
      hi += G;
    } else if (r == CUDA_SUCCESS && q + G == lo) {
      lo = q;
    } else {
      fprintf(stderr, "bend: 1 GiB managed chunk %llu -> %d at %llx, heap so far [%llx, %llx)\\n",
        (unsigned long long)(at / G), (int)r, (unsigned long long)q,
        (unsigned long long)lo, (unsigned long long)hi);
      err_fail("corpus reservation failed");
    }
#if CUDA_VERSION >= 13000
    cuMemAdvise(q, G, CU_MEM_ADVISE_SET_PREFERRED_LOCATION,
      (CUmemLocation){ CU_MEM_LOCATION_TYPE_DEVICE, gpu_dev });
#else
    cuMemAdvise(q, G, CU_MEM_ADVISE_SET_PREFERRED_LOCATION, gpu_dev);
#endif
  }
  return (u64*)(uintptr_t)lo;
}
'''
s, n = re.subn(r"static u64\* gpu_map\(u64 bytes\) \{\n  CUdeviceptr p = 0;\n  if \(cuMemAllocManaged.*?\n\}\n",
               lambda m: new, s, count=1, flags=re.S)
if n:
    open(p, "w").write(s)
    print("chunked gpu_map:", p, file=sys.stderr)
"""

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
    # The shim also rewrites the CUDA heap as 1 GiB managed allocations
    # (CHUNKED), the most Modal's sandbox grants in one.
    pathlib.Path("/tmp/shim").mkdir(parents=True, exist_ok=True)
    pathlib.Path("/tmp/shim/chunked.py").write_text(CHUNKED)
    pathlib.Path("/tmp/shim/clang").write_text(
        "#!/bin/sh\nfor a in \"$@\"; do case \"$a\" in *.c) python3 /tmp/shim/chunked.py \"$a\";; esac; done\n"
        f"exec /usr/lib/llvm-{LLVM}/bin/clang \"$@\" $BEND_TUNE\n")
    sh("chmod +x /tmp/shim/clang && cp /tmp/shim/clang /tmp/shim/cc")
    shim = {"PATH": "/tmp/shim:" + os.environ["PATH"], "BEND_TUNE": TUNE}
    sh("mkdir -p bench/build && python3 tools/gen_blake3.py", cwd=bend)
    sh("bend bench/mem.bend -o bench/build/mem", cwd=bend, env=shim)
    sh("RUSTFLAGS='-C target-cpu=native' cargo build --release --quiet", cwd=f"{bend}/bench/rust")
    sh(f"ref/cuda/build.sh {work}/b3cuda", cwd=bend)
    mem = f"{bend}/bench/build/mem"
    ref = f"{bend}/bench/rust/target/release/b3ref"
    cuda = f"{work}/b3cuda"
    # the official test vectors, on the native CUDA reference and on Bend's GPU path
    vec = {"cuda": sh(f"{cuda} vectors 4 | python3 test/check.py", cwd=bend).strip().splitlines()[-1]}
    print(vec, flush=True)

    rows = []
    for d in range(24, max_log + 1):
        size = 4 << d
        heap = max(4, 3 * (size >> 30) + 2)
        g_ms, g_dig = runs(sh(f"{mem} +RTS --gpu {heap}GB -RTS {d} {reps} 1"))
        c_ms, c_dig = runs(sh(f"{mem} +RTS --gpu off -RTS {d} {reps} 0"))
        r_ms, r_dig = runs(sh(f"{ref} {d} {reps} 0"))
        n_ms, n_dig = runs(sh(f"{cuda} mem {d} {reps} 4"))
        b_ms, b_dig = runs(sh(f"{cuda} mem {d} {reps} 0"))
        digests = g_dig | c_dig | r_dig | n_dig | b_dig
        row = {
            "bytes": size,
            "bend_gpu": summary(g_ms),
            "bend_cpu": summary(c_ms),
            "rust_cpu": summary(r_ms),
            "native_cuda": summary(n_ms),
            "native_cuda_bend_shape": summary(b_ms),
            "digest": sorted(digests)[0],
            "digests_agree": len(digests) == 1,
        }
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("bytes", "digests_agree")}),
              {k: row[k]["min_ms"] for k in SIDES}, flush=True)
    one = 28 if max_log >= 28 else max_log
    single = {
        "bytes": 4 << one,
        "bend_cpu_1t": summary(runs(sh(f"{mem} +RTS --gpu off --threads 1 -RTS {one} 3 0"))[0]),
        "rust_cpu_1t": summary(runs(sh(f"{ref} {one} 3 2"))[0]),
    }
    return {"info": info, "vectors": vec, "rows": rows, "single_thread": single,
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

HEAP = r"""
#include <cuda.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double now(void) { struct timespec q; clock_gettime(CLOCK_MONOTONIC, &q); return q.tv_sec + q.tv_nsec * 1e-9; }
#define T(what) fprintf(stderr, "%8.3f ms %s -> %d\n", (now() - t0) * 1e3, what, (int)r)
int main(int argc, char** argv) {
  size_t bytes = (size_t)atol(argv[1]) << 20;
  CUresult r; CUdevice d; CUcontext c; CUdeviceptr p = 0;
  double t0 = now();
  r = cuInit(0); r = cuDeviceGet(&d, 0); r = cuDevicePrimaryCtxRetain(&c, d); r = cuCtxSetCurrent(c); T("context");
  r = cuMemAllocManaged(&p, bytes, CU_MEM_ATTACH_GLOBAL); T("cuMemAllocManaged");
  r = cuMemAdvise(p, bytes, CU_MEM_ADVISE_SET_PREFERRED_LOCATION, (CUmemLocation){ CU_MEM_LOCATION_TYPE_DEVICE, d }); T("cuMemAdvise");
  r = cuMemsetD8(p, 0, 64 << 20); r = cuCtxSynchronize(); T("memset 64 MB on device");
  memset((char*)(uintptr_t)p + bytes - (64 << 20), 1, 64 << 20); r = 0; T("host writes last 64 MB");
  r = cuMemFree(p); T("free");
  return 0;
}
"""

CHUNKS = r"""
#include <cuda.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double now(void) { struct timespec q; clock_gettime(CLOCK_MONOTONIC, &q); return q.tv_sec + q.tv_nsec * 1e-9; }
int main(int argc, char** argv) {
  int n = atoi(argv[1]);
  CUdevice d; CUcontext c; CUdeviceptr p[64], dev = 0;
  cuInit(0); cuDeviceGet(&d, 0); cuDevicePrimaryCtxRetain(&c, d); cuCtxSetCurrent(c);
  double t0 = now();
  for (int i = 0; i < n; i++) {
    CUresult r = cuMemAllocManaged(&p[i], 1ull << 30, CU_MEM_ATTACH_GLOBAL);
    fprintf(stderr, "%8.3f ms chunk %d -> %d at %llx%s\n", (now() - t0) * 1e3, i, (int)r,
            (unsigned long long)p[i], i && p[i] == p[i - 1] + (1ull << 30) ? " (follows)" : i && p[i] + (1ull << 30) == p[i - 1] ? " (precedes)" : "");
  }
  CUresult r = cuMemAlloc(&dev, 8ull << 30);
  fprintf(stderr, "%8.3f ms cuMemAlloc 8 GB device -> %d\n", (now() - t0) * 1e3, (int)r);
  return 0;
}
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


@app.function(gpu="L4", cpu=8, memory=32768, timeout=1200)
def debug_advise() -> str:
    """Does Bend's CUDA runtime hang because of its cuMemAdvise? Rebuild
    pow2! with bend's own clang command, the advise removed, and run it."""
    log = []

    def step(name, cmd, cwd="/work", env=None, limit=120):
        t = time.time()
        try:
            r = subprocess.run(["bash", "-lc", cmd], cwd=cwd, env={**os.environ, **(env or {})},
                               capture_output=True, text=True, timeout=limit)
            out = f"exit {r.returncode}\n{r.stdout[-2500:]}\n{r.stderr[-1500:]}"
        except subprocess.TimeoutExpired:
            out = f"TIMEOUT after {limit}s"
        log.append(f"== {name} ({time.time() - t:.1f}s)\n{out}")
        print(log[-1], flush=True)
        return out.startswith("exit 0")

    os.makedirs("/work/shim", exist_ok=True)
    pathlib.Path("/work/pow2.bend").write_text(POW2)
    pathlib.Path("/work/shim/clang").write_text(
        f"#!/bin/sh\necho \"$@\" >> /work/clang.log\nexec /usr/lib/llvm-{LLVM}/bin/clang \"$@\"\n")
    os.chmod("/work/shim/clang", 0o755)
    shim = {"PATH": "/work/shim:" + os.environ["PATH"]}
    step("bend build (logged)", "bend pow2.bend -o pow2 && cat clang.log", env=shim)
    step("emit C", "bend pow2.bend -o pow2.c && grep -n 'cuMemAdvise' pow2.c")
    # bend's own compile command, on the patched C
    cmd = [l for l in pathlib.Path("/work/clang.log").read_text().splitlines() if ".c" in l and "-o" in l][-1]
    src = [a for a in cmd.split() if a.endswith(".c")][0]
    step("patch: drop cuMemAdvise", "sed -i 's/^  cuMemAdvise(/  if (0) cuMemAdvise(/' pow2.c && grep -n 'cuMemAdvise' pow2.c")
    out = [a for a in cmd.split() if a.startswith("/work/")][0]
    step("compile patched", f"/usr/lib/llvm-{LLVM}/bin/clang " + cmd.replace(src, "pow2.c").replace(out, "/work/pow2_noadvise")
         + " && cp pow2.gpu pow2_noadvise.gpu && ls -la pow2_noadvise*")
    step("compile with symbols", "bend pow2.bend -o pow2g.c && " + f"/usr/lib/llvm-{LLVM}/bin/clang "
         + cmd.replace(src, "pow2g.c").replace(out, "/work/pow2g").replace("-O3", "-O1 -g -fno-inline")
         + " && cp pow2.gpu pow2g.gpu")
    step("run pow2! as built by bend", "./pow2", limit=30)
    step("run pow2! without cuMemAdvise", "./pow2_noadvise", limit=30)
    # print the device's progress as the host sees it, after every sync
    trace = r'''
import re, sys
p = "/work/pow2t.c"
s = open("/work/pow2g.c").read()
s = s.replace("""    if (cuCtxSynchronize() != CUDA_SUCCESS) {
      err_fail("device fault");
    }""", """    CUresult sr = cuCtxSynchronize();
    { static int k; if (k++ < 40) fprintf(stderr, "sync %d n=%u -> %d front=%llu root=%u err=%u cursor=%u\\n", k, n, (int)sr,
        (unsigned long long)H[H_FRONT], a32_load(a32_at(H, H_ROOT_DONE)), a32_load(a32_at(H, H_ERROR_CODE)), a32_load(a32_at(H, H_CURSOR))); }
    if (sr != CUDA_SUCCESS) {
      err_fail("device fault");
    }""", 1)
T = '{ struct timespec q; clock_gettime(CLOCK_MONOTONIC, &q); fprintf(stderr, "%8.3f %s\\n", q.tv_sec + q.tv_nsec * 1e-9, WHAT); }'
def mark(what):
    return T.replace('WHAT', '"' + what + '"')
for anchor, what in [("  CORPUS     = gpu ? gpu_map(size) : corpus_map(size);", "mapped"),
                     ("  corpus_lay(H, size);", "laid out"),
                     ("    gpu_load(size);", "gpu program loaded")]:
    s = s.replace(anchor, anchor + "\n  " + mark(what), 1)
s = s.replace("  io_loop(corpus_setup(why == NULL, thr, mem));", "  " + mark("probed") + "\n  io_loop(corpus_setup(why == NULL, thr, mem));", 1)
s = s.replace("""  while (!root_done(H)) {
    if (f == 0) {""", """  fprintf(stderr, "cube_run gpu=%d f=%u CUBE_LOG=%u\\n", (int)gpu, f, CUBE_LOG);
  while (!root_done(H)) {
    { static int k; if (k++ < 20) fprintf(stderr, "cube loop f=%u front=%llu\\n", f, (unsigned long long)H[H_FRONT]); }
    if (f == 0) {""", 1)
open(p, "w").write(s)
print("patched", s.count("sync %d"), s.count("cube_run gpu"))
'''
    pathlib.Path("/work/trace.py").write_text(trace)
    step("instrument", "python3 trace.py")
    step("compile instrumented", f"/usr/lib/llvm-{LLVM}/bin/clang "
         + cmd.replace(src, "pow2t.c").replace(out, "/work/pow2t").replace("-O3", "-O1 -g")
         + " && cp pow2.gpu pow2t.gpu")
    for size in ["1GB"]:
        step(f"run instrumented, {size} heap", f"timeout 30 ./pow2t +RTS --gpu {size} -RTS; echo status=$?", limit=40)
    pathlib.Path("/work/heap.c").write_text(HEAP)
    step("compile heap probe", "cc -O2 -I/usr/local/cuda/include heap.c -L/usr/local/cuda/lib64 -lcuda -o heap")
    for mb in [1024, 1025, 1536]:
        step(f"heap probe {mb} MB", f"timeout 20 ./heap {mb}; echo status=$?", limit=30)
    pathlib.Path("/work/chunks.c").write_text(CHUNKS)
    step("compile chunk probe", "cc -O2 -I/usr/local/cuda/include chunks.c -L/usr/local/cuda/lib64 -lcuda -o chunks")
    step("chunk probe 16 x 1 GB managed", "timeout 60 ./chunks 16; echo status=$?", limit=70)
    return "\n".join(log)


@app.local_entrypoint()
def main(gpu: str = "L4", max_log: int = 28, reps: int = 6, debug_only: bool = False,
         debug_advise_only: bool = False):
    if debug_advise_only:
        print(debug_advise.with_options(gpu=gpu).remote())
        return
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
    print("| bytes | Bend CUDA | native CUDA | native CUDA, Bend's shape | Bend CPU | Rust blake3 CPU | digests |")
    print("|------:|----------:|------------:|--------------------------:|---------:|----------------:|:-------:|")
    for r in res["rows"]:
        cells = " | ".join(f"{r[k]['min_ms']:.2f} ms" for k in SIDES)
        print(f"| {r['bytes'] >> 20} MiB | {cells} | {'ok' if r['digests_agree'] else 'DIFFER'} |")
    s = res["single_thread"]
    print(f"\n1 thread, {s['bytes'] >> 20} MiB: Bend {s['bend_cpu_1t']['min_ms']:.1f} ms, "
          f"Rust {s['rust_cpu_1t']['min_ms']:.1f} ms")
    print(f"wrote {out} ({res['wall_s']} s)")
