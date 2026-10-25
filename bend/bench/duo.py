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
"""
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DUO = os.path.join(HERE, "build", "duo")


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


def main():
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
