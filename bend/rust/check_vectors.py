#!/usr/bin/env python3
"""Checks a turboblake binary against the official BLAKE3 test vectors, the
release smoke test: python3 bend/rust/check_vectors.py BIN [VECTORS] [WORKDIR]

Each vector's input (len bytes of i % 251) is written to a file and all of
them are hashed in one run, the engine's many-files path; then stdin, the
extended output (--length) against the vectors, and a --check round trip.
Exits 1 on any mismatch. Lives outside bend/crate, which gen.sh regenerates."""
import json, os, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
binary = sys.argv[1]
vectors = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "..", "..", "test_vectors", "test_vectors.json")
work = sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="turboblake-vectors-")
os.makedirs(work, exist_ok=True)

cases = json.load(open(vectors))["cases"]
paths = []
for c in cases:
    path = os.path.join(work, f"v{c['input_len']}.bin")
    with open(path, "wb") as f:
        f.write(bytes(i % 251 for i in range(c["input_len"])))
    paths.append(path)

lines = subprocess.run([binary, *paths], capture_output=True, text=True, check=True).stdout.splitlines()
bad = sum(1 for c, p, line in zip(cases, paths, lines) if line != f"{c['hash'][:64]}  {p}")
bad += abs(len(lines) - len(cases))
print(f"files: {len(cases) - bad}/{len(cases)} test vectors match")

stdin = subprocess.run([binary], input=b"abc", capture_output=True, check=True).stdout.decode().split()[0]
want = "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"
print(f"stdin: {'ok' if stdin == want else 'MISMATCH ' + stdin}")
bad += stdin != want

# Extended output goes through upstream's code: compare the full vector.
longest = max(cases, key=lambda c: c["input_len"])
xof = subprocess.run([binary, "--no-names", f"--length={len(longest['hash']) // 2}", paths[cases.index(longest)]],
                     capture_output=True, text=True, check=True).stdout.strip()
print(f"--length: {'ok' if xof == longest['hash'] else 'MISMATCH'}")
bad += xof != longest["hash"]

sums = os.path.join(work, "SUMS")
with open(sums, "w") as f:
    f.write("\n".join(lines) + "\n")
check = subprocess.run([binary, "--check", "--quiet", sums], capture_output=True, text=True)
print(f"--check: {'ok' if check.returncode == 0 and not check.stdout else 'FAILED ' + check.stdout + check.stderr}")
bad += check.returncode != 0

sys.exit(1 if bad else 0)
