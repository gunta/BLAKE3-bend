"""The drop-in packages on Linux x86-64, on Modal (CPU only: cents a run).

Builds libturboblake (bend/lib) with LLVM clang on Ubuntu, runs its test
suite (the official vectors in every mode and split, and random inputs
against the official b3sum) and its benchmark against the official C
library; generates the turboblake crate, runs upstream's own tests through
the engine and races it against the official crate. Prints the logs.

    modal run bend/bench/modal_linux.py                        # lib, rust
    modal run bend/bench/modal_linux.py --steps go,python,node  # the bindings

`go` also builds the Linux engine objects for the Go module
(bend/go/engine_linux_{amd64,arm64}.syso) and writes them here.
"""

import pathlib
import subprocess
import time

import modal

_HERE = pathlib.Path(__file__).resolve()
REPO = _HERE.parents[2] if modal.is_local() else pathlib.Path("/repo")
LLVM = 20
GO = "1.27.2"
NODE = "26.12.0"
BUN = "1.4.3"

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("curl", "ca-certificates", "wget", "gnupg", "lsb-release",
                 "software-properties-common", "build-essential", "unzip", "xz-utils",
                 "libc6-dev-arm64-cross", "libgcc-13-dev-arm64-cross")
    .run_commands(
        f"wget -qO /tmp/llvm.sh https://apt.llvm.org/llvm.sh && bash /tmp/llvm.sh {LLVM}",
        "curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal",
        "curl -fsSL https://bend-lang.com/install.sh | BEND_NO_TELEMETRY=1 sh",
        f"curl -fsSL https://go.dev/dl/go{GO}.linux-amd64.tar.gz | tar -C /usr/local -xz",
        f"curl -fsSL https://nodejs.org/dist/v{NODE}/node-v{NODE}-linux-x64.tar.xz"
        " | tar -xJ -C /usr/local --strip-components=1",
        f"curl -fsSL https://bun.sh/install | bash -s bun-v{BUN}",
        "pip install pytest numpy",
    )
    .env({
        "PATH": f"/root/.bend/bin:/root/.cargo/bin:/root/.bun/bin:/usr/local/go/bin:"
                f"/usr/lib/llvm-{LLVM}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
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

app = modal.App("turboblake-linux", image=image)


@app.function(cpu=16, memory=32768, timeout=3600)
def check(steps: str = "lib,rust") -> dict:
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
        if step("build libturboblake", "bend/lib/build.sh"):
            step("test", "TURBOBLAKE_TRACE=1 python3 bend/lib/test.py --big")
            step("bench", "python3 bend/lib/bench.py 9")
            step("trace 1 GiB", "for n in 1048576 67108864 1073741824; do "
                 "TURBOBLAKE_TRACE=1 bend/lib/build/bench/bend $n 5; done")
    if "rust" in steps:
        step("generate turboblake", "bend/rust/gen.sh")
        step("upstream tests through the engine",
             "TURBOBLAKE_MIN=2048 TURBOBLAKE_TRACE=1 cargo test --release "
             "--features rayon,mmap,traits-preview 2>&1 | grep -E '^test result|FAILED|panicked|turboblake:'",
             cwd="/work/bend/crate")
        step("the same failing test, upstream's crate (gVisor has no /sys/kernel/btf)",
             "cargo test --release --features mmap test_unmappable 2>&1 | grep -E '^test |test result'",
             cwd="/work")
        step("rust bench", "cargo build --release --quiet 2>/dev/null; ./target/release/turboblake-bench 7",
             cwd="/work/bend/rust/bench")
    files = {}
    if "go" in steps:
        # the prebuilt engines for Linux: amd64 here, arm64 against the cross sysroot
        slp = ("-mllvm -slp-max-reg-size=512 -mllvm -slp-recursion-max-depth=100000 "
               "-mllvm -slp-threshold=-20 -mllvm -inline-threshold=20000")
        step("go: csrc", "bend/lib/gen.sh >/dev/null && rm -rf bend/go/csrc && cp -R bend/lib/csrc bend/go/csrc")
        for goarch, flags in (("amd64", "-march=x86-64-v3"),
                              ("arm64", "--target=aarch64-linux-gnu --sysroot=/usr/aarch64-linux-gnu "
                                        "-mcpu=neoverse-n1")):
            out = f"bend/go/engine_linux_{goarch}.syso"
            if step(f"go: engine_linux_{goarch}.syso",
                    f"clang -x c -std=c11 -O3 {flags} {slp} -fPIC -w -DBEND_EMBED -Dmain=b3e_bend_main "
                    f"-c bend/go/csrc/engine.c -o {out} && ls -la {out}"):
                files[out] = pathlib.Path(f"/work/{out}").read_bytes()
        step("go: gen.sh (amd64 again, and c_engine.c)", "bend/go/gen.sh && head -1 bend/go/c_engine.c")
        step("go test", "go test -count=1 ./... 2>&1 | tail -5", cwd="/work/bend/go")
        step("go bench", "go run . 2>&1 | tail -12", cwd="/work/bend/go/bench")
        files["bend/bench/results/lang-go-linux.json"] = pathlib.Path(
            "/work/bend/bench/results/lang-go.json").read_bytes()
    if "python" in steps:
        step("python: build", "pip install -q . 2>&1 | tail -3", cwd="/work/bend/python")
        step("python: blake3-py's tests",
             "TURBOBLAKE_MIN=2048 python -m pytest -q /work/bend/python/tests 2>&1 | tail -3 && "
             "python -m pytest -q /work/bend/python/tests 2>&1 | tail -1", cwd="/tmp")
    if "node" in steps:
        step("node: build", "npm install --silent 2>&1 | tail -3; ls build/*.node", cwd="/work/bend/node")
        step("node: test", "node test/test.mjs && bun test/test.mjs", cwd="/work/bend/node")
        step("node: bench", "node bench.mjs 2>&1 | tail -10", cwd="/work/bend/node")
    return {"log": "\n".join(log), "files": files}


@app.local_entrypoint()
def main(steps: str = "lib,rust"):
    res = check.remote(steps)
    print(res["log"])
    for rel, data in res["files"].items():
        (REPO / rel).write_bytes(data)
        print(f"wrote {rel} ({len(data)} bytes)")
