#!/usr/bin/env python3
"""CPU + GPU on one input at once (split.bend, bench/duo.bend).

Starts the GPU side and the CPU side (the leader) of bench/build/duo for
each plan, and prints the median round with its digest. A plan is
"j:bits": bit i of bits (from the low end) gives the left child at spine
depth i to the GPU (1) or the CPU (0), bit j the remainder; j >= 1, so the
root is a parent the leader folds. "1:3" is all GPU, "1:0" all CPU, "2:3"
gives the GPU 3/4 of a power-of-two input. "0:G" splits by slices instead:
the GPU takes the first G of 16 (1..15) on all its lanes.

usage: bend/bench/duo.py [d=28] [reps=15] [lv=6] [threads] plan...
env:   DUO_GPU_HEAP=6GB  the GPU side's heap (+RTS --gpu), for d >= 29

--native runs libturboblake's split instead (ADR 0017): one process, the
Bend engine on the CPU side and the native Metal or CUDA kernel on the GPU
side (bench/duo_native.c over bend/lib/build). Its plans: "cpu" (the engine
alone), "gpu" (the input in GPU memory, the kernel alone), "split" (memory
the GPU reads, shared at the share the measured rates balance), "split=F"
(the GPU takes F of it). The plans run interleaved, `cycles` processes each
(env DUO_CYCLES, default 5), and the medians skip each process's first round.

usage: bend/bench/duo.py --native [d=28] [reps=8] [--json out.json] plan...
"""
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DUO = os.path.join(HERE, "build", "duo")
NATIVE = os.path.join(HERE, "build", "duo_native")
LIB = os.path.join(ROOT, "bend", "lib", "build")


def run(d, reps, plan, lv, threads, blk):
    j, bits = plan.split(":")
    args = [str(d), str(reps), j, bits, str(lv)]
    env = dict(os.environ, B3DUO=blk)
    rts = ["+RTS", "--gpu", "off"] + (["--threads", str(threads)] if threads else []) + ["-RTS"]
    lead = subprocess.Popen([DUO] + rts + args + ["0"], env=env,
                            stdout=subprocess.PIPE, text=True)
    heap = os.environ.get("DUO_GPU_HEAP")
    grts = ["+RTS", "--gpu", heap, "-RTS"] if heap else []
    follow = subprocess.Popen([DUO] + grts + args + ["1"], env=env,
                              stdout=subprocess.PIPE, text=True)
    out, _ = lead.communicate()
    fout, _ = follow.communicate()
    if lead.returncode or follow.returncode:
        sys.exit(f"duo failed for plan {plan}: {lead.returncode} {follow.returncode}")
    # "us T gpu K DIGEST cpu_us C": the first round warms up.
    rows = [line.split() for line in out.splitlines() if line.startswith("us ")][1:]
    gpu = [int(line.split()[1]) for line in fout.splitlines() if line.startswith("gpu_us ")][1:]
    us = [int(r[1]) for r in rows]
    cpu = [int(r[6]) for r in rows]
    digests = {r[4] for r in rows}
    return (statistics.median(us), min(us), statistics.median(cpu),
            statistics.median(gpu), digests)


def build_native():
    if not os.path.exists(os.path.join(LIB, "lib", "libblake3.a")):
        subprocess.run([os.path.join(ROOT, "bend", "lib", "build.sh")], check=True)
    os.makedirs(os.path.dirname(NATIVE), exist_ok=True)
    libs = ["-lpthread", "-lm"] + (["-ldl"] if sys.platform.startswith("linux") else [])
    subprocess.run([os.environ.get("CC", "clang"), "-O2", "-I", os.path.join(LIB, "include"),
                    os.path.join(HERE, "duo_native.c"), os.path.join(LIB, "lib", "libblake3.a"),
                    *libs, "-o", NATIVE], check=True)


def run_native(d, reps, plan):
    mode, _, share = plan.partition("=")
    env = dict(os.environ)
    if share:
        env["TURBOBLAKE_GPU_SHARE"] = share
    r = subprocess.run([NATIVE, str(d), str(reps), mode], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"plan {plan} failed ({r.returncode}): {r.stderr.strip()[-300:]}", flush=True)
        return [], set()
    rows = [line.split() for line in r.stdout.splitlines() if line.startswith("us ")][1:]
    return [int(x[1]) for x in rows], {x[2] for x in rows}


def native(args):
    out_json = None
    if "--json" in args:
        i = args.index("--json")
        out_json = args[i + 1]
        args = args[:i] + args[i + 2:]
    nums = [a for a in args if a.isdigit()]
    plans = [a for a in args if not a.isdigit()] or ["cpu", "gpu", "split"]
    d = int(nums[0]) if nums else 28
    reps = int(nums[1]) if len(nums) > 1 else 8
    cycles = int(os.environ.get("DUO_CYCLES", "5"))
    build_native()
    print(f"2^{d} words ({4 << d >> 20} MiB), {cycles} x {reps} rounds a plan, interleaved")
    times = {p: [] for p in plans}
    digests = {p: set() for p in plans}
    for _ in range(cycles):
        for plan in plans:
            t, dg = run_native(d, reps, plan)
            times[plan] += t
            digests[plan] |= dg
    rows = []
    for plan in plans:
        if not times[plan]:
            continue
        med, best = statistics.median(times[plan]), min(times[plan])
        rows.append({"plan": plan, "bytes": 4 << d, "median_ms": med / 1000, "min_ms": best / 1000,
                     "runs_ms": [t / 1000 for t in times[plan]], "digests": sorted(digests[plan])})
        print(f"plan {plan:>10}: median {med / 1000:7.2f} ms, best {best / 1000:7.2f}  "
              f"{' '.join(x[:16] for x in sorted(digests[plan]))}")
    agree = len(set().union(*digests.values())) == 1
    print("digests agree" if agree else "DIGESTS DIFFER")
    if out_json:
        import json
        with open(out_json, "w") as f:
            json.dump({"bytes": 4 << d, "cycles": cycles, "reps": reps, "digests_agree": agree,
                       "rows": rows}, f, indent=1)
            f.write("\n")
        print(f"wrote {out_json}")
    sys.exit(0 if agree else 1)


def main():
    if "--native" in sys.argv:
        return native([a for a in sys.argv[1:] if a != "--native"])
    nums = [a for a in sys.argv[1:] if ":" not in a]
    plans = [a for a in sys.argv[1:] if ":" in a] or ["1:3", "1:0", "2:3"]
    d = int(nums[0]) if len(nums) > 0 else 28
    reps = int(nums[1]) if len(nums) > 1 else 15
    lv = int(nums[2]) if len(nums) > 2 else 6
    threads = int(nums[3]) if len(nums) > 3 else 0
    blk = os.path.join(tempfile.gettempdir(), f"b3duo-{os.getpid()}")
    print(f"2^{d} words ({4 << d >> 20} MiB), {reps} rounds, GPU leaves lv={lv}")
    for plan in plans:
        med, best, cpu, gpu, digests = run(d, reps, plan, lv, threads, blk)
        print(f"plan {plan:>6}: median {med / 1000:6.2f} ms, best {best / 1000:6.2f} "
              f"(cpu share {cpu / 1000:6.2f}, gpu share {gpu / 1000:6.2f})  "
              f"{' '.join(d[:16] for d in sorted(digests))}")
    if os.path.exists(blk):
        os.unlink(blk)


if __name__ == "__main__":
    main()
