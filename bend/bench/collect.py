#!/usr/bin/env python3
"""Folds the GPU and language benchmarks' raw results into results.json.

The site reads only results.json. This writes four of its sections from the
files the benchmarks write, so no number is copied by hand:

  gpu_metal       Bend's GPU path on the M5 Pro against hand-written Metal,
                  with the CPU sides (gpu_reference and in_memory)
  gpu_nvidia      the same on NVIDIA GPUs (modal-<gpu>.json, modal_gpu.py)
  deepseek_linux  b3sum against turboblake on DeepSeek-sized files on Linux
                  (modal-deepseek.json, modal_deepseek.py)
  languages       one table per environment (lang-*.json): turboblake, the
                  BLAKE3 packages it replaces, and other hashes for scale
  versus          1 GiB on the fastest GPU measured and on the Mac, from
                  SHA-256 to the GPU (modal-B200.json, modal-sha-B200.json,
                  the Mac's tables above)

A table: {title, machine, unit, note, rows: [{input, <series>: ms}],
series: {<key>: {label, kind, description}}}. kind is "bend" (turboblake),
"blake3" (an alternative) or "other" (another hash function).

    python3 bend/bench/collect.py
"""
import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE / "results"

SIZES = [1 << 10, 64 << 10, 1 << 20, 16 << 20, 256 << 20, 1 << 30]

OTHER = {
    "sha256": "SHA-256", "sha512": "SHA-512", "sha1": "SHA-1", "md5": "MD5",
    "blake2b": "BLAKE2b", "blake2s": "BLAKE2s", "sha3_256": "SHA3-256",
}


def size_label(n):
    return f"{n >> 30} GiB" if n >= 1 << 30 else f"{n >> 20} MiB" if n >= 1 << 20 else f"{n >> 10} KiB"


def load(name):
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else None


# Each language: its file, the machine, and impl name -> (key, label, kind,
# description). Keys starting with "bend" are turboblake's.
LANGS = {
    "c": ("lang-c.json", "C (blake3.h)", {
        "libturboblake": ("bend", "libturboblake", "bend", "the official C library with the Bend engine"),
        "official C": ("official", "official C", "blake3", "the official C library: SIMD, one thread"),
    }),
    "rust": ("lang-rust.json", "Rust", {
        "turboblake hash": ("bend", "turboblake hash", "bend", "blake3::hash on turboblake"),
        "turboblake update_rayon": ("bend_rayon", "turboblake update_rayon", "bend", "Hasher::update_rayon on turboblake"),
        "blake3 hash": ("blake3", "blake3 hash", "blake3", "the official crate's hash: one thread"),
        "blake3 update_rayon": ("blake3_rayon", "blake3 update_rayon", "blake3", "the official crate on every core (rayon)"),
    }),
    "python": ("lang-python.json", "Python", {
        "turboblake": ("bend", "turboblake", "bend", "pip install turboblake (import blake3)"),
        "blake3 (PyPI)": ("pypi", "blake3 (PyPI)", "blake3", "the Rust-based blake3 module, default max_threads=1"),
        "blake3 (PyPI), max_threads=AUTO": ("pypi_auto", "blake3 (PyPI), AUTO", "blake3", "the same, max_threads=blake3.AUTO"),
        **{f"hashlib.{k}": (k, v, "other", f"hashlib.{k}") for k, v in OTHER.items()},
    }),
    "node": ("lang-node.json", "Node.js", {
        "turboblake": ("bend", "turboblake", "bend", "the native addon"),
        "turboblake (Bend's JS)": ("bend_js", "turboblake, Bend's JS", "bend", "Bend's BLAKE3 emitted to JavaScript (browsers)"),
        "@napi-rs/blake-hash": ("napi_rs", "@napi-rs/blake-hash", "blake3", "native, Rust, one thread"),
        "hash-wasm": ("hash_wasm", "hash-wasm", "blake3", "WebAssembly"),
        "@noble/hashes": ("noble", "@noble/hashes", "blake3", "pure JavaScript"),
        "crypto sha256": ("sha256", "SHA-256", "other", "node:crypto"),
        "crypto sha512": ("sha512", "SHA-512", "other", "node:crypto"),
        "crypto sha1": ("sha1", "SHA-1", "other", "node:crypto"),
        "crypto md5": ("md5", "MD5", "other", "node:crypto"),
        "crypto blake2b512": ("blake2b", "BLAKE2b", "other", "node:crypto"),
        "crypto blake2s256": ("blake2s", "BLAKE2s", "other", "node:crypto"),
        "crypto sha3-256": ("sha3_256", "SHA3-256", "other", "node:crypto"),
    }),
    "go": ("lang-go.json", "Go", {
        "turboblake": ("bend", "turboblake", "bend", "github.com/gunta/BLAKE3-bend/bend/go"),
        "lukechampine.com/blake3": ("luke", "lukechampine.com/blake3", "blake3", "Go assembly, every core for big inputs"),
        "github.com/zeebo/blake3": ("zeebo", "github.com/zeebo/blake3", "blake3", "Go assembly, one thread"),
        "crypto/sha256": ("sha256", "SHA-256", "other", "crypto/sha256"),
        "crypto/sha512": ("sha512", "SHA-512", "other", "crypto/sha512"),
        "crypto/sha1": ("sha1", "SHA-1", "other", "crypto/sha1"),
        "crypto/md5": ("md5", "MD5", "other", "crypto/md5"),
        "x/crypto/blake2b": ("blake2b", "BLAKE2b", "other", "golang.org/x/crypto/blake2b"),
        "x/crypto/blake2s": ("blake2s", "BLAKE2s", "other", "golang.org/x/crypto/blake2s"),
        "crypto/sha3 (256)": ("sha3_256", "SHA3-256", "other", "crypto/sha3"),
    }),
}
# Bun runs Node's benchmark; Linux runs are kept apart from the Mac's.
LANGS["bun"] = ("lang-bun.json", "Bun", LANGS["node"][2])
LANGS["go_linux"] = ("lang-go-linux.json", "Go on Linux", LANGS["go"][2])


def lang_table(lang, mac):
    file, title, names = LANGS[lang]
    raw = load(file)
    if raw is None:
        return None
    info = raw.get("info", {})
    rows, series = {}, {}
    for r in raw["rows"]:
        if r["impl"] not in names or r["bytes"] not in SIZES:
            continue
        key, label, kind, desc = names[r["impl"]]
        series[key] = {"label": label, "kind": kind, "description": desc}
        rows.setdefault(r["bytes"], {"input": size_label(r["bytes"])})[key] = round(r["ms"], 4)
    if "linux" in lang:
        machine = f"Linux x86-64, {info.get('cpus', '?')} vCPUs (Modal)"
    else:
        machine = mac
    runtime = info.get("runtime") or info.get("go") or info.get("python")
    return {
        "title": title, "machine": machine, "unit": "ms",
        "note": "One-shot hash of an in-memory buffer, medians of interleaved runs, same digest for every BLAKE3."
                + (f" {runtime}." if runtime else ""),
        "rows": [rows[n] for n in SIZES if n in rows],
        "series": series,
    }


def nvidia(gpu):
    raw = load(f"modal-{gpu}.json")
    if raw is None:
        return None
    i = raw["info"]
    keys = {
        "bend_gpu": ("Bend, CUDA", "bend", "hash1! on Bend's CUDA runtime"),
        "native_cuda": ("native CUDA", "blake3", "hand-written CUDA (bend/ref/cuda)"),
        "native_cuda_bend_shape": ("native CUDA, Bend's leaves", "blake3", "the same kernel run in hash1!'s leaf shape"),
        "bend_cpu": (f"Bend, CPU ({i['cpus']} cores)", "bend", "the 8-lane CPU tree"),
        "rust_cpu": (f"Rust blake3, CPU ({i['cpus']} cores)", "blake3", "the official crate, SIMD + rayon"),
    }
    rows = []
    for r in raw["rows"]:
        row = {"input": size_label(r["bytes"])}
        for k in keys:
            if k in r:
                row["bend_cpu" if k == "bend_cpu" else k] = round(r[k]["median_ms"], 3)
        rows.append(row)
    return {
        "title": i["gpu"].split(",")[0], "machine": f"{i['gpu'].split(',')[0]} on Modal, {i['cpus']} x86 cores",
        "unit": "ms",
        "note": "Warm, in memory, the same digest from every side; medians, the first run (moving pages onto the GPU) left out.",
        "rows": rows,
        "series": {k: {"label": v[0], "kind": v[1], "description": v[2]} for k, v in keys.items()},
    }


def metal(results):
    ref = results["gpu_reference"]
    cpu = {r["input"].split(",")[0]: r for r in results["in_memory"]["rows"] if "all cores" in r["input"]}
    rows = []
    for r in ref["rows"]:
        c = cpu.get(r["input"], {})
        rows.append({"input": r["input"], "bend_gpu": r.get("bend_gpu"), "metal": r.get("metal"),
                     "metal_bend_leaves": r.get("metal_bend_leaves"), "bend_cpu": c.get("bend_cpu"),
                     "rust": c.get("rust")})
    return {
        "title": "Apple M5 Pro", "machine": f"{results['machine']['name']}, {results['machine']['gpu']}",
        "unit": "ms", "note": ref.get("note", ""),
        "rows": rows,
        "series": {
            "bend_gpu": {"label": "Bend, Metal", "kind": "bend", "description": "hash1! on the 20-core GPU"},
            "metal": {"label": "native Metal", "kind": "blake3", "description": "hand-written Metal (bend/ref/metal)"},
            "metal_bend_leaves": {"label": "native Metal, Bend's leaves", "kind": "blake3", "description": "the same kernel in hash1!'s leaf shape"},
            "bend_cpu": {"label": "Bend, CPU (18 cores)", "kind": "bend", "description": "the 8-lane CPU tree"},
            "rust": {"label": "Rust blake3, CPU (18 cores)", "kind": "blake3", "description": "the official crate, NEON + rayon"},
        },
    }


def deepseek():
    raw = load("modal-deepseek.json")
    if raw is None:
        return None
    rows = []
    for name, w in raw["workloads"].items():
        rows.append({"input": f"{name.replace('DeepSeek ', '')} ({w['bytes'] / 1e9:.1f} GB)",
                     "b3sum": round(statistics.median(w["b3sum_ms"]) / 1000, 2),
                     "bend": round(statistics.median(w["bend_ms"]) / 1000, 2)})
    return {
        "title": "DeepSeek-sized files on Linux", "machine": f"Linux x86-64, {raw['info']['cpus']} vCPUs (Modal)",
        "unit": "s",
        "note": "Synthetic shards at the real files' sizes (bench/synth.c), one-shot, identical output. Modal's sandbox "
                "keeps written files in memory, so this is the cached case; the Mac's run of the real 101.5 GB shard "
                "measures the uncached one.",
        "rows": rows,
        "series": {"b3sum": {"label": "b3sum", "kind": "blake3", "description": "the official b3sum 1.8.7"},
                   "bend": {"label": "turboblake", "kind": "bend", "description": "turboblake 1.8.7"}},
    }


# SHA-256 at 1 GiB in each of the Mac's language runs: the fastest one stands for SHA-256.
MAC_SHA256 = {"python": ("hashlib.sha256", "Python's hashlib"), "node": ("crypto sha256", "Node's crypto"),
              "bun": ("crypto sha256", "Bun's crypto"), "go": ("crypto/sha256", "Go's crypto/sha256")}


def versus(results):
    """1 GiB in memory on the B200 and on the Mac: SHA-256 (one core, the most it can use), the official
    BLAKE3 on one core and on every core, and turboblake on the CPU, on Bend's GPU path and on the native
    GPU kernel. One row per machine; `machines` says what each column was on it."""
    G = 1 << 30
    series = {
        "sha256": {"label": "SHA-256", "kind": "other",
                   "description": "the fastest SHA-256 measured on the machine, with the CPU's SHA instructions; one core, since each block waits for the one before"},
        "blake3": {"label": "BLAKE3, one core", "kind": "blake3", "description": "the official blake3 crate on one thread"},
        "blake3_all": {"label": "BLAKE3, every core", "kind": "blake3", "description": "the official blake3 crate on every core (rayon)"},
        "bend_cpu": {"label": "turboblake, CPU", "kind": "bend", "description": "Bend's 8-lane tree on every core"},
        "bend_gpu": {"label": "turboblake, Bend on the GPU", "kind": "bend", "description": "Bend's GPU path (hash1!)"},
        "bend_native": {"label": "turboblake, native GPU kernel", "kind": "bend",
                        "description": "the hand-written CUDA or Metal kernel in bend/ref (ADR 0013)"},
    }
    rows, machines = [], []

    b200, sha = load("modal-B200.json"), load("modal-sha-B200.json")
    r = next((r for r in (b200 or {}).get("rows", []) if r["bytes"] == G), None)
    s = next((r for r in (sha or {}).get("rows", []) if r["bytes"] == G), None)
    one = (b200 or {}).get("single_thread", {})
    if r and s and one.get("bytes") == G:
        cores = b200["info"]["cpus"]
        rows.append({"input": "NVIDIA B200", "sha256": s["sha256"]["median_ms"],
                     "blake3": round(one["rust_cpu_1t"]["median_ms"], 3),
                     "blake3_all": round(r["rust_cpu"]["median_ms"], 3), "bend_cpu": round(r["bend_cpu"]["median_ms"], 3),
                     "bend_gpu": round(r["bend_gpu"]["median_ms"], 3), "bend_native": round(r["native_cuda"]["median_ms"], 3)})
        machines.append({"id": "b200", "title": "NVIDIA B200", "where": f"on Modal, {cores} x86 cores",
                         "api": "CUDA", "cores": cores,
                         "sha256": f"OpenSSL {sha['info']['openssl'].split()[1]} (Python's hashlib)"
                                   + (", SHA-NI" if sha["info"].get("sha_ni") else ""),
                         "gpu_memory": True})

    shas = []
    for lang, (impl, name) in MAC_SHA256.items():
        raw = load(LANGS[lang][0])
        ms = next((x["ms"] for x in (raw or {}).get("rows", []) if x["impl"] == impl and x["bytes"] == G), None)
        if ms is not None:
            shas.append((ms, name))
    mem = {x["input"]: x for x in results["in_memory"]["rows"]}
    ref = {x["input"]: x for x in results["gpu_reference"]["rows"]}
    one, every, gpu = mem.get("1 GiB, 1 core"), mem.get("1 GiB, all cores"), ref.get("1 GiB")
    if shas and one and every and gpu:
        ms, name = min(shas)
        rows.append({"input": results["machine"]["name"], "sha256": round(ms, 3), "blake3": one["rust"],
                     "blake3_all": every["rust"], "bend_cpu": every["bend_cpu"],
                     "bend_gpu": gpu["bend_gpu"], "bend_native": gpu["metal"]})
        machines.append({"id": "metal", "title": results["machine"]["name"], "where": "18 cores, 20-core GPU",
                         "api": "Metal", "cores": 18, "sha256": f"{name} (OpenSSL), ARMv8 SHA-2 instructions",
                         "gpu_memory": False})
    if not rows:
        return None
    return {
        "title": "1 GiB, from SHA-256 to the GPU", "input": "1 GiB", "unit": "ms",
        "note": "One 1 GiB buffer already in memory, hashed once per run; medians. Every BLAKE3 side gives the same "
                "digest. On the B200 the GPU sides read the buffer from the GPU's own memory (the first run, which "
                "moves it there, is left out); SHA-256 there is a separate run on the same Modal B200 host. On the "
                "Mac, CPU and GPU share one memory.",
        "rows": rows, "machines": machines, "series": series,
    }


def main():
    path = RES / "results.json"
    results = json.loads(path.read_text())
    mac = "Apple M5 Pro, 18 cores"
    results["gpu_metal"] = metal(results)
    results["gpu_nvidia"] = [t for t in (nvidia("B200"), nvidia("L4")) if t]
    ds = deepseek()
    if ds:
        results["deepseek_linux"] = ds
    results["languages"] = {k: t for k in LANGS if (t := lang_table(k, mac))}
    vs = versus(results)
    if vs:
        results["versus"] = vs
    results["status_note"] = ("Numbers from 2026-10-26. NVIDIA: Bend's CUDA runtime on Modal's B200 and L4, "
                              "with its heap in 1 GiB pieces (Modal's sandbox grants no bigger managed allocation).")
    path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {path}: gpu_metal, gpu_nvidia ({len(results['gpu_nvidia'])}), "
          f"languages ({', '.join(results['languages'])})" + (", deepseek_linux" if ds else "")
          + (f", versus ({', '.join(r['input'] for r in vs['rows'])})" if vs else ""))


if __name__ == "__main__":
    main()
