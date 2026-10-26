"""DeepSeek-sized model shards on a Linux box, on Modal, without the download.

Races the official `b3sum` (BLAKE3 1.8.7, built from this repository's
b3sum/) against `turboblake` (the crate in bend/crate, built from source)
on stand-ins for deepseek-ai/DeepSeek-V4.1-Flash-1017's shards 1-6 (31.3 GB)
and shard 48 (101.5 GB, bigger than the container's 64 GiB of memory),
written at their exact sizes by bench/synth.c in seconds instead of fetched.
Both tools must print the same lines. Writes
bend/bench/results/modal-deepseek.json and prints a table.

CPU only, so it is cheap (a few cents a run), but still billed: run it on
purpose.

    modal run bend/bench/modal_deepseek.py                 # both workloads
    modal run bend/bench/modal_deepseek.py --small         # shards 1-2, a smoke test
"""

import json
import os
import pathlib
import statistics
import subprocess
import time

import modal

_HERE = pathlib.Path(__file__).resolve()
REPO = _HERE.parents[2] if modal.is_local() else pathlib.Path("/repo")
LLVM = 20
CPUS = 16

# The real shards' sizes, so the trees (and the segment edges) are theirs.
SHARDS = {
    "model-00001-of-00048.safetensors": 970533624,
    "model-00002-of-00048.safetensors": 1323858272,
    "model-00003-of-00048.safetensors": 7389759032,
    "model-00004-of-00048.safetensors": 7389759032,
    "model-00005-of-00048.safetensors": 7405953784,
    "model-00006-of-00048.safetensors": 7389759032,
    "model-00048-of-00048.safetensors": 101537926640,
}

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("curl", "ca-certificates", "wget", "gnupg", "lsb-release",
                 "software-properties-common", "build-essential", "util-linux")
    .run_commands(
        f"wget -qO /tmp/llvm.sh https://apt.llvm.org/llvm.sh && bash /tmp/llvm.sh {LLVM}",
        "curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal",
    )
    .env({
        "PATH": f"/root/.cargo/bin:/usr/lib/llvm-{LLVM}/bin:/usr/local/sbin:/usr/local/bin:"
                "/usr/sbin:/usr/bin:/sbin:/bin",
        "CC": "clang",
    })
    .add_local_dir(REPO, "/repo", ignore=[
        ".git", "**/target", "**/build", "bend/bench/data", "site/node_modules",
        "site/dist", "media", "**/.DS_Store", ".claude", "**/node_modules",
    ])
)

app = modal.App("turboblake-deepseek", image=image)

# Drops a file's pages from the page cache (posix_fadvise DONTNEED) and
# prints the fraction still resident (mincore on 4096 sampled pages), so
# each side starts on the SSD, not in RAM.
EVICT = r"""
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
int main(int argc, char** argv) {
  long pg = sysconf(_SC_PAGESIZE);
  for (int i = 1; i < argc; i++) {
    int fd = open(argv[i], O_RDONLY);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) != 0) { perror(argv[i]); return 1; }
    posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);
    unsigned char* at = mmap(NULL, st.st_size, PROT_READ, MAP_SHARED, fd, 0);
    unsigned long pages = (st.st_size + pg - 1) / pg, n = pages < 4096 ? pages : 4096, hit = 0;
    for (unsigned long k = 0; at != MAP_FAILED && k < n; k++) {
      unsigned char v = 0;
      if (mincore(at + (k * pages / n) * pg, pg, &v) == 0 && (v & 1)) hit++;
    }
    printf("%s %.3f\n", argv[i], n ? (double)hit / n : 0.0);
    if (at != MAP_FAILED) munmap(at, st.st_size);
    close(fd);
  }
  return 0;
}
"""


def sh(cmd, cwd=None):
    t = time.time()
    r = subprocess.run(["bash", "-lc", cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"`{cmd}` failed ({r.returncode}):\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")
    print(f"[{time.time() - t:6.1f}s] {cmd[:120]}", flush=True)
    return r.stdout


def timed(cmd):
    t = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True)
    return (time.perf_counter() - t) * 1000, r.stdout, r.returncode


@app.function(cpu=CPUS, memory=65536, ephemeral_disk=512 * 1024, timeout=3600)
def race(rounds: int = 2, small: bool = False) -> dict:
    work, data = "/work", "/data"
    sh(f"rm -rf {work} && cp -r /repo {work} && mkdir -p {data}")
    info = {
        "cpu": sh("lscpu | sed -n 's/^Model name:[ ]*//p' | head -1").strip() or "unknown",
        "cpus": int(sh("nproc").strip()),
        "memory": sh("free -g | sed -n 2p").split()[1] + " GiB",
        "disk": sh(f"df -h {data} | tail -1").split()[1],
        "clang": sh("clang --version | head -1").strip(),
        "kernel": sh("uname -r").strip(),
    }
    print(info, flush=True)
    sh("cargo build --release --quiet", cwd=f"{work}/b3sum")
    sh("cargo build --release --quiet", cwd=f"{work}/bend/crate")
    sh(f"cc -O3 -pthread -o {work}/synth {work}/bend/bench/synth.c")
    pathlib.Path(f"{work}/evict.c").write_text(EVICT)
    sh(f"cc -O2 -o {work}/evict {work}/evict.c")
    official = f"{work}/b3sum/target/release/b3sum"
    bend = f"{work}/bend/crate/target/release/turboblake"
    info["b3sum"] = sh(f"{official} --version").strip()

    names = list(SHARDS)[:2] if small else list(SHARDS)
    gen = {}
    for i, name in enumerate(names):
        out = sh(f"{work}/synth {data}/{name} {SHARDS[name]} {i + 1} {CPUS}")
        gen[name] = out.strip()
        print(out.strip(), flush=True)

    workloads = {"DeepSeek shards 1-6": names[:6]} if not small else {"DeepSeek shards 1-2": names}
    if not small:
        workloads["DeepSeek 101 GB shard"] = [names[6]]
    results = {}
    for wl, files in workloads.items():
        paths = [f"{data}/{f}" for f in files]
        sides = {"b3sum": [official] + paths, "bend": [bend] + paths}
        runs = {k: [] for k in sides}
        resident = {k: [] for k in sides}
        outs = {}
        for r in range(rounds):
            for k, cmd in sides.items():
                ev = sh(f"{work}/evict " + " ".join(paths))
                resident[k].append(max(float(line.split()[1]) for line in ev.splitlines()))
                ms, out, rc = timed(cmd)
                if rc != 0:
                    raise RuntimeError(f"{k} exited {rc} on {wl}")
                outs.setdefault(k, out)
                runs[k].append(ms)
                print(f"{wl} round {r + 1} {k}: {ms / 1000:.2f} s (resident before {resident[k][-1]:.0%})",
                      flush=True)
        same = outs["b3sum"] == outs["bend"]
        size = sum(SHARDS[f] for f in files)
        results[wl] = {
            "files": files,
            "bytes": size,
            "b3sum_ms": runs["b3sum"],
            "bend_ms": runs["bend"],
            "resident_before": resident,
            "b3sum_median_ms": statistics.median(runs["b3sum"]),
            "bend_median_ms": statistics.median(runs["bend"]),
            "output_identical": same,
            "output": outs["bend"].decode().splitlines(),
        }
        if not same:
            print("OUTPUTS DIFFER\n", outs["b3sum"].decode(), "\n", outs["bend"].decode(), flush=True)
    return {"info": info, "generate": gen, "workloads": results,
            "note": "one-shot runs, interleaved, each after posix_fadvise(DONTNEED) on the "
                    "inputs; files written by bench/synth.c at the real shards' sizes"}


@app.local_entrypoint()
def main(rounds: int = 2, small: bool = False):
    t = time.time()
    res = race.remote(rounds, small)
    res["wall_s"] = round(time.time() - t, 1)
    out = REPO / "bend" / "bench" / "results" / ("modal-deepseek-small.json" if small else "modal-deepseek.json")
    out.write_text(json.dumps(res, indent=2) + "\n")
    i = res["info"]
    print(f"\n{i['cpu']} x{i['cpus']} | {i['memory']} | {i['b3sum']}")
    print("| input | b3sum | turboblake | | output |")
    print("|---|---:|---:|---:|:---:|")
    for wl, r in res["workloads"].items():
        b, n = r["b3sum_median_ms"] / 1000, r["bend_median_ms"] / 1000
        print(f"| {wl}, {r['bytes'] / 1e9:.1f} GB | {b:.2f} s | {n:.2f} s | {b / n:.2f}x | "
              f"{'identical' if r['output_identical'] else 'DIFFER'} |")
    print(f"wrote {out} ({res['wall_s']} s)")
