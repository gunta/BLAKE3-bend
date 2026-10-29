// The prebuilt addons: the turboblake package carries one turboblake.node
// for each platform below, in prebuilds/<platform>/, each built for that
// platform's baseline CPU as the release binaries are (the engine checks the
// CPU before it runs, and an older one hashes as upstream does). index.js
// loads the one for this machine; with none, turboblake runs on Bend's
// JavaScript, and `node build.mjs` in the package builds an addon here.
//
//   node prebuilt.mjs name        this machine's platform (darwin-arm64, linux-x64-musl, ...)
//   node prebuilt.mjs pack DIR    build/turboblake.node into DIR/prebuilds/<platform>/
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// Each platform with a prebuilt addon, and the CPU its engine is built for
// (.github/workflows/turboblake-build.yml passes it as TURBOBLAKE_TARGET_CPU).
// Windows has no engine yet: its addon is the official C alone (ADR 0020).
export const platforms = {
  "darwin-arm64": "-mcpu=apple-m1",
  "darwin-x64": "-march=x86-64-v3",
  "linux-x64-gnu": "-march=x86-64-v3",
  "linux-arm64-gnu": "-mcpu=generic",
  "linux-x64-musl": "-march=x86-64-v3",
  "linux-arm64-musl": "-mcpu=generic",
  "win32-x64": "",
  "win32-arm64": "",
};

// musl or glibc: a glibc process reports the glibc it runs on.
function libc() {
  try {
    return globalThis.process.report.getReport().header.glibcVersionRuntime ? "gnu" : "musl";
  } catch {
    return "gnu";
  }
}

export function platform() {
  const { platform: os, arch } = globalThis.process;
  return os === "linux" ? `${os}-${arch}-${libc()}` : `${os}-${arch}`;
}

// The addons to try on this machine, best first: on Linux the other libc's
// too, should a runtime report its libc wrongly (the wrong one fails to load).
export function candidates() {
  const p = platform();
  if (!p.startsWith("linux-")) return [p];
  return [p, p.endsWith("-gnu") ? p.replace(/-gnu$/, "-musl") : p.replace(/-musl$/, "-gnu")];
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("prebuilt.mjs")) {
  const [cmd, out] = process.argv.slice(2);
  if (cmd === "name") {
    console.log(platform());
  } else if (cmd === "pack" && out) {
    const p = platform();
    if (!(p in platforms)) throw new Error(`turboblake: no prebuilt addon for ${p}`);
    const addon = join(here, "build", "turboblake.node");
    if (!existsSync(addon)) throw new Error("turboblake: build/turboblake.node is missing (node build.mjs)");
    const dir = join(out, "prebuilds", p);
    mkdirSync(dir, { recursive: true });
    cpSync(addon, join(dir, "turboblake.node"));
    console.log(join(dir, "turboblake.node"));
  } else {
    console.error("usage: node prebuilt.mjs name | pack DIR");
    process.exit(2);
  }
}
