#!/usr/bin/env python3
"""Fetches Hugging Face files for the benchmarks, resumably.

Each file is preallocated and filled by parallel HTTP range requests (one
connection tops out near 40 MB/s here, eight near the link's 100 MB/s),
written in place with os.pwrite. Finished 64 MiB pieces are logged in
<file>.parts, so a rerun resumes. At the end the size, and the SHA-256 the
Hub lists for LFS files, are checked.

usage: bench/hf_fetch.py <repo> <dest-dir> <file> [file ...]
"""

import concurrent.futures as cf
import hashlib
import json
import os
import pathlib
import sys
import threading
import time
import urllib.request

PIECE = 64 << 20
CONNS = 8


def meta(repo):
    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true"
    with urllib.request.urlopen(url, timeout=60) as r:
        return {f["path"]: f for f in json.load(r) if f.get("type") == "file"}


def fetch_piece(url, fd, off, n):
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={off}-{off + n - 1}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                got = 0
                while got < n:
                    buf = r.read(min(4 << 20, n - got))
                    if not buf:
                        raise IOError("short read")
                    os.pwrite(fd, buf, off + got)
                    got += len(buf)
            return
        except Exception as e:
            time.sleep(2 * (attempt + 1))
            last = e
    raise last


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(16 << 20)
            if not b:
                return h.hexdigest()
            h.update(b)


def fetch(repo, dest, name, info):
    url = f"https://huggingface.co/{repo}/resolve/main/{name}"
    size = info["size"]
    path = dest / name
    path.parent.mkdir(parents=True, exist_ok=True)
    log = path.with_name(path.name + ".parts")
    done = set(int(x) for x in log.read_text().split()) if log.exists() else set()
    if path.exists() and path.stat().st_size == size and not log.exists():
        print(f"have {name}", flush=True)
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    os.ftruncate(fd, size)
    todo = [off for off in range(0, size, PIECE) if off not in done]
    lock = threading.Lock()
    t0 = time.time()
    moved = [0]

    def one(off):
        n = min(PIECE, size - off)
        fetch_piece(url, fd, off, n)
        with lock:
            done.add(off)
            moved[0] += n
            with open(log, "a") as f:
                f.write(f"{off}\n")
            if len(done) % 32 == 0 or len(done) * PIECE >= size:
                rate = moved[0] / max(time.time() - t0, 1e-3) / 1e6
                print(f"{name}: {min(len(done) * PIECE, size) / 1e9:.1f}/{size / 1e9:.1f} GB "
                      f"at {rate:.0f} MB/s", flush=True)

    with cf.ThreadPoolExecutor(CONNS) as ex:
        list(ex.map(one, todo))
    os.close(fd)
    want = (info.get("lfs") or {}).get("oid")
    if want:
        got = sha256(path)
        if got != want:
            sys.exit(f"{name}: sha256 {got} != {want}")
        print(f"{name}: sha256 ok", flush=True)
    log.unlink(missing_ok=True)


def main():
    repo, dest, names = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3:]
    files = meta(repo)
    for n in names:
        if n not in files:
            sys.exit(f"{repo} has no {n}")
    # small files first, then the rest in order
    for n in sorted(names, key=lambda n: files[n]["size"]):
        fetch(repo, dest, n, files[n])
    print("all done", flush=True)


if __name__ == "__main__":
    main()
