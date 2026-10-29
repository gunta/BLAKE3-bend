// The prebuilt addons on npm: one small package per platform
// (@turboblake/darwin-arm64, ...), each holding a turboblake.node built for
// that platform's baseline CPU, as the release binaries are. turboblake
// lists them as optionalDependencies, so npm, Bun, pnpm and Deno fetch only
// the one that matches; with none, `npm install` builds the addon here
// (build.mjs) and, failing that, turboblake runs on Bend's JavaScript.
//
//   node prebuilt.mjs name              the package for this machine
//   node prebuilt.mjs pack OUT          build/turboblake.node into OUT/<name>/
//   node prebuilt.mjs installed         exit 0 if this machine's package is there
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// The platforms with a prebuilt addon, and the CPU each is built for
// (.github/workflows/turboblake-release.yml passes it as TURBOBLAKE_TARGET_CPU).
export const platforms = {
  "darwin-arm64": { os: "darwin", cpu: "arm64", flags: "-mcpu=apple-m1" },
  "darwin-x64": { os: "darwin", cpu: "x64", flags: "-march=x86-64-v3" },
  "linux-x64-gnu": { os: "linux", cpu: "x64", libc: "glibc", flags: "-march=x86-64-v3" },
  "linux-arm64-gnu": { os: "linux", cpu: "arm64", libc: "glibc", flags: "-mcpu=generic" },
};

export function packageName() {
  const p = `${process.platform}-${process.arch}`;
  return `@turboblake/${process.platform === "linux" ? `${p}-gnu` : p}`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [cmd, out] = process.argv.slice(2);
  if (cmd === "name") {
    console.log(packageName());
  } else if (cmd === "installed") {
    try {
      createRequire(import.meta.url).resolve(packageName());
    } catch {
      process.exit(1);
    }
  } else if (cmd === "pack" && out) {
    const main = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
    const name = packageName();
    const p = platforms[name.slice("@turboblake/".length)];
    if (!p) throw new Error(`turboblake: no prebuilt package for ${name}`);
    const addon = join(here, "build", "turboblake.node");
    if (!existsSync(addon)) throw new Error("turboblake: build/turboblake.node is missing (node build.mjs)");
    const dir = join(out, name.slice(1).replace("/", "-"));
    mkdirSync(dir, { recursive: true });
    cpSync(addon, join(dir, "turboblake.node"));
    for (const f of ["LICENSE_A2", "LICENSE_A2LLVM", "LICENSE_CC0"]) {
      cpSync(join(here, "..", "..", f), join(dir, f));
    }
    writeFileSync(join(dir, "README.md"),
      `# ${name}\n\nThe prebuilt native addon of [turboblake](https://www.npmjs.com/package/turboblake) for ${p.os} ${p.cpu}` +
      `${p.libc ? ` (${p.libc})` : ""}, built for \`${p.flags}\`. Install \`turboblake\`, not this package.\n`);
    writeFileSync(join(dir, "package.json"), JSON.stringify({
      name,
      version: main.version,
      description: `turboblake's native addon for ${p.os} ${p.cpu}${p.libc ? ` (${p.libc})` : ""}`,
      main: "turboblake.node",
      files: ["turboblake.node", "LICENSE_*"],
      os: [p.os],
      cpu: [p.cpu],
      ...(p.libc ? { libc: [p.libc] } : {}),
      engines: main.engines,
      homepage: main.homepage,
      repository: main.repository,
      license: main.license,
    }, null, 2) + "\n");
    console.log(dir);
  } else {
    console.error("usage: node prebuilt.mjs name | installed | pack OUT");
    process.exit(2);
  }
}
