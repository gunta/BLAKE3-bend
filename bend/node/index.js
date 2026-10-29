// turboblake: BLAKE3 for Node, Bun and Deno on libturboblake, the official C
// library whose big inputs go to the Bend engine on every core: two drop-in
// faces (api.js) over one native addon (src/addon.c), and hashFiles(paths),
// many files at once as the turboblake command does. With no addon (it could
// not be built here) the same faces run on Bend's own JavaScript (js/).
import { createRequire } from "node:module";
import { faces } from "./api.js";
import { candidates } from "./prebuilt.mjs";

// An addon built here (build.mjs) first, then the one prebuilt for this
// platform (prebuilds/, prebuilt.mjs). TURBOBLAKE_JS=1 picks the
// JavaScript engine even with an addon there.
let native = null;
if (globalThis.process?.env?.TURBOBLAKE_JS !== "1") {
  const require = createRequire(import.meta.url);
  for (const id of ["./build/turboblake.node", ...candidates().map((p) => `./prebuilds/${p}/turboblake.node`)]) {
    try {
      native = require(id);
      break;
    } catch {}
  }
}

const engine = native === null ? (await import("./js/engine.js")).engine : {
  name: "native",
  init: (mode, k) => native.init(mode, k),
  update: native.update,
  finalize: native.finalize,
  clone: (state) => state.slice(0),
  hash: native.hash,
};

export const { blake3, BLAKE3, HashReader, Hasher, createHash, createKeyed, createDeriveKey, hash,
  keyedHash, deriveKey } = faces(engine);
export const backend = engine.name;
export default blake3;

// Many files at once
// ------------------

// Each file's BLAKE3 hash (a Uint8Array), opened, mapped or read in
// parallel, files not in the page cache streamed, every file's tree at once;
// or an Error for a file that could not be read. A pipe or device is read
// with the hasher instead.
export async function hashFiles(paths) {
  const rs = native === null ? null : native.hashFiles(paths.map(String));
  return Promise.all(paths.map(async (p, i) => {
    const r = rs === null ? -1 : rs[i];
    if (r instanceof Uint8Array) return r;
    if (r !== -1) {
      const e = new Error(`${p}: os error ${r}`);
      e.errno = r;
      e.path = String(p);
      return e;
    }
    const { createReadStream } = await import("node:fs");
    const h = new BLAKE3();
    try {
      for await (const chunk of createReadStream(p)) h.update(chunk);
    } catch (e) {
      // the POSIX number for the error's name: on Windows Node's errno is
      // libuv's (-4058 for ENOENT), not the 2 the engine reports elsewhere
      const { constants } = await import("node:os");
      e.errno = constants.errno[e.code] ?? Math.abs(e.errno ?? 5);
      e.path = String(p);
      return e;
    }
    return h.digest();
  }));
}

