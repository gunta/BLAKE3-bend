// Builds build/turboblake.node: src/addon.c over libturboblake (the C in
// ./csrc, or ../lib/csrc in the repository), with clang. The engine gets
// bend/build.sh's vectorizer flags. Run by `npm install` (with --optional:
// a failure is a warning, and turboblake runs on Bend's JavaScript instead);
// needs clang and the Node-API headers (Node's own, or node-api-headers).
// TURBOBLAKE_PORTABLE=1 builds for the baseline CPU instead of this one;
// TURBOBLAKE_NO_GPU=1 leaves out the GPU backend (turboblake_gpu.c, which
// loads Metal or CUDA at run time, ADR 0017).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, cpSync } from "node:fs";
import { createRequire } from "node:module";
import { arch, platform } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// in the repository, always the current C; in a package, the copy it ships
let csrc = join(here, "csrc");
if (existsSync(join(here, "..", "lib", "csrc", "engine.c"))) {
  cpSync(join(here, "..", "lib", "csrc"), csrc, { recursive: true });
}

function nodeApiInclude() {
  const own = join(dirname(dirname(process.execPath)), "include", "node");
  if (existsSync(join(own, "node_api.h"))) return own;
  try {
    return createRequire(import.meta.url)("node-api-headers").include_dir;
  } catch {
    throw new Error("turboblake: no Node-API headers (install node-api-headers)");
  }
}

const cc = process.env.CC || "clang";
const x86 = arch() === "x64";
const cpu = process.env.TURBOBLAKE_PORTABLE ? [] : [x86 ? "-march=native" : "-mcpu=native"];
const slp = ["-mllvm", "-slp-max-reg-size=512", "-mllvm", "-slp-recursion-max-depth=100000",
  "-mllvm", "-slp-threshold=-20", "-mllvm", "-inline-threshold=20000"];
const out = join(here, "build");
mkdirSync(out, { recursive: true });
const optional = process.argv.includes("--optional");
const run = (args) => {
  console.log([cc, ...args].join(" "));
  try {
    execFileSync(cc, args, { stdio: "inherit" });
  } catch (e) {
    if (!optional) throw e;
    console.warn("turboblake: could not build the native addon; using Bend's JavaScript engine (slower)");
    process.exit(0);
  }
};

const objs = [];
const compile = (src, flags) => {
  const obj = join(out, basename(src) + ".o");
  run([...flags, "-fPIC", "-c", src, "-o", obj]);
  objs.push(obj);
};
compile(join(csrc, "engine.c"), ["-x", "c", "-std=c11", "-O3", ...cpu, "-w", "-DBEND_EMBED",
  "-Dmain=b3e_bend_main", ...slp]);
const gpu = !process.env.TURBOBLAKE_NO_GPU;
const c = ["-O3", "-std=c11", ...cpu, "-DTURBOBLAKE", ...(gpu ? ["-DTURBOBLAKE_GPU"] : []), `-I${csrc}`];
const glue = gpu ? ["turboblake.c", "turboblake_gpu.c"] : ["turboblake.c"];
for (const f of ["blake3.c", "blake3_dispatch.c", "blake3_portable.c", ...glue]) {
  compile(join(csrc, f), [...c, ...(x86 ? [] : ["-DBLAKE3_USE_NEON=1"])]);
}
if (x86) {
  for (const s of ["sse2", "sse41", "avx2", "avx512"]) compile(join(csrc, `blake3_${s}_x86-64_unix.S`), []);
} else {
  compile(join(csrc, "blake3_neon.c"), [...c, "-DBLAKE3_USE_NEON=1"]);
}
compile(join(here, "src", "addon.c"), [...c, `-I${nodeApiInclude()}`, "-DNODE_GYP_MODULE_NAME=turboblake"]);
const link = platform() === "darwin" ? ["-bundle", "-undefined", "dynamic_lookup"] : ["-shared"];
const dl = gpu && platform() === "linux" ? ["-ldl"] : [];
run([...link, ...objs, "-lpthread", "-lm", ...dl, "-o", join(out, "turboblake.node")]);
