"""The drop-in packages on Linux x86-64, on Modal (CPU only: cents a run).

Builds libblake3-bend (bend/lib) with LLVM clang on Ubuntu, runs its test
suite (the official vectors in every mode and split, and random inputs
against the official b3sum) and its benchmark against the official C
library; generates the blake3-bend crate, runs upstream's own tests through
the engine and races it against the official crate. Prints the logs.

    modal run bend/bench/modal_linux.py
"""

import pathlib
import subprocess
import time

import modal

_HERE = pathlib.Path(__file__).resolve()
REPO = _HERE.parents[2] if modal.is_local() else pathlib.Path("/repo")
LLVM = 20

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("curl", "ca-certificates", "wget", "gnupg", "lsb-release",
                 "software-properties-common", "build-essential", "unzip")
    .run_commands(
        f"wget -qO /tmp/llvm.sh https://apt.llvm.org/llvm.sh && bash /tmp/llvm.sh {LLVM}",
        "curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal",
        "curl -fsSL https://bend-lang.com/install.sh | BEND_NO_TELEMETRY=1 sh",
    )
    .env({
        "PATH": f"/root/.bend/bin:/root/.cargo/bin:/usr/lib/llvm-{LLVM}/bin:/usr/local/sbin:"
                "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "CC": "clang",
        "BEND_NO_TELEMETRY": "1",
        "JSC_maxPerThreadStackUsage": "60000000",
        "BUN_JSC_maxPerThreadStackUsage": "60000000",
    })
    .add_local_dir(REPO, "/repo", ignore=[
        ".git", "**/target", "**/build", "bend/bench/data", "site/node_modules",
        "site/dist", "media", "**/.DS_Store", ".claude", "**/node_modules",
    ])
)

app = modal.App("blake3-bend-linux", image=image)


@app.function(cpu=16, memory=32768, timeout=3600)
def check(steps: str = "lib,rust") -> str:
    log = []

    def step(name, cmd, cwd="/work"):
        t = time.time()
        r = subprocess.run(["bash", "-lc", f"ulimit -s 65520; {cmd}"], cwd=cwd,
                           capture_output=True, text=True)
        log.append(f"== {name} ({time.time() - t:.1f}s, exit {r.returncode})\n"
                   f"{r.stdout[-6000:]}{r.stderr[-3000:]}")
        print(log[-1], flush=True)
        return r.returncode == 0

    subprocess.run("rm -rf /work && cp -r /repo /work", shell=True, check=True)
    step("machine", "lscpu | grep -E 'Model name|^CPU\\(s\\)|Flags' | cut -c1-200; free -g | head -2")
    step("official b3sum", "cargo build --release --quiet", cwd="/work/b3sum")
    if "lib" in steps:
        if step("build libblake3-bend", "bend/lib/build.sh"):
            step("test", "BLAKE3_BEND_TRACE=1 python3 bend/lib/test.py --big")
            step("bench", "python3 bend/lib/bench.py 9")
            step("trace 1 GiB", "for n in 1048576 67108864 1073741824; do "
                 "BLAKE3_BEND_TRACE=1 bend/lib/build/bench/bend $n 5; done")
    if "rust" in steps:
        step("generate blake3-bend", "bend/rust/gen.sh")
        step("upstream tests through the engine",
             "BLAKE3_BEND_MIN=2048 BLAKE3_BEND_TRACE=1 cargo test --release "
             "--features rayon,mmap,traits-preview 2>&1 | grep -E '^test result|FAILED|panicked|blake3-bend:'",
             cwd="/work/bend/rust/blake3-bend")
        step("the same failing test, upstream's crate (gVisor has no /sys/kernel/btf)",
             "cargo test --release --features mmap test_unmappable 2>&1 | grep -E '^test |test result'",
             cwd="/work")
        step("rust bench", "cargo build --release --quiet 2>/dev/null; ./target/release/blake3-bend-bench 7",
             cwd="/work/bend/rust/bench")
    return "\n".join(log)


@app.local_entrypoint()
def main(steps: str = "lib,rust"):
    print(check.remote(steps))
