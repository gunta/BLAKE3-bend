// b3bend: BLAKE3 for Node, Bun and Deno on libblake3-bend, the official C
// library whose big inputs go to the Bend engine on every core.
//
// Two drop-in faces over one native addon (src/addon.c):
//   - blake3(msg, { dkLen, key, context }) and blake3.create(opts), as
//     @noble/hashes/blake3.js exports them;
//   - hash, keyedHash, deriveKey, createHash, createKeyed, createDeriveKey,
//     as the blake3 package on npm exports them.
// And hashFiles(paths): many files at once, as the b3bend command does.
import { createRequire } from "node:module";

const native = createRequire(import.meta.url)("./build/b3bend.node");

const HASH = 0, KEYED = 1, DERIVE = 2;
const enc = new TextEncoder();

function bytes(data, what = "input") {
  if (data instanceof Uint8Array) return data;
  if (typeof data === "string") return enc.encode(data);
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  throw new TypeError(`b3bend: ${what} must be a Uint8Array, a TypedArray, an ArrayBuffer or a string`);
}

function stateFor(opts = {}) {
  if (opts.key !== undefined && opts.context !== undefined) {
    throw new Error("b3bend: use either key or context, not both");
  }
  if (opts.key !== undefined) return native.init(KEYED, bytes(opts.key, "key"));
  if (opts.context !== undefined) return native.init(DERIVE, bytes(opts.context, "context"));
  return native.init(HASH);
}

function outLen(n, fallback = 32) {
  if (n === undefined) return fallback;
  if (!Number.isSafeInteger(n) || n < 0) throw new RangeError("b3bend: bad output length");
  return n;
}

// @noble/hashes
// -------------

export class BLAKE3 {
  constructor(opts = {}, state) {
    this.blockLen = 64;
    this.outputLen = outLen(opts.dkLen);
    this.canXOF = true;
    this.state = state ?? stateFor(opts);
    this.posOut = 0;
    this.finished = false;
    this.destroyed = false;
  }
  update(data) {
    if (this.destroyed) throw new Error("b3bend: hash instance has been destroyed");
    if (this.finished) throw new Error("b3bend: digest() has already been called");
    native.update(this.state, bytes(data));
    return this;
  }
  digestInto(out) {
    if (this.finished) throw new Error("b3bend: digest() has already been called");
    this.finished = true;
    native.finalize(this.state, out, 0);
    return out;
  }
  digest() {
    return this.digestInto(new Uint8Array(this.outputLen));
  }
  xofInto(out) {
    if (this.destroyed) throw new Error("b3bend: hash instance has been destroyed");
    if (this.finished && this.posOut === 0) throw new Error("b3bend: XOF is not possible after digest()");
    this.finished = true;
    native.finalize(this.state, out, this.posOut);
    this.posOut += out.length;
    return out;
  }
  xof(n) {
    return this.xofInto(new Uint8Array(outLen(n)));
  }
  clone() {
    return this._cloneInto();
  }
  _cloneInto(to) {
    const state = this.state.slice(0);
    if (to === undefined) to = new BLAKE3({ dkLen: this.outputLen }, state);
    else to.state = state;
    to.outputLen = this.outputLen;
    to.posOut = this.posOut;
    to.finished = this.finished;
    to.destroyed = this.destroyed;
    return to;
  }
  destroy() {
    this.destroyed = true;
    new Uint8Array(this.state).fill(0);
  }
}

export const blake3 = Object.assign(
  (msg, opts) => {
    if (opts === undefined || (opts.key === undefined && opts.context === undefined)) {
      const out = new Uint8Array(outLen(opts?.dkLen));
      native.hash(bytes(msg), out);
      return out;
    }
    const h = new BLAKE3(opts);
    return h.update(msg).digest();
  },
  { create: (opts) => new BLAKE3(opts), outputLen: 32, blockLen: 64, canXOF: true },
);

// npm blake3
// ----------

function out(buf, encoding) {
  const b = Buffer.from(buf.buffer, buf.byteOffset, buf.byteLength);
  return encoding === undefined ? b : b.toString(encoding);
}

export class HashReader {
  constructor(state) {
    this.state = state;
    this.position = 0n;
  }
  readInto(target) {
    native.finalize(this.state, target, Number(this.position));
    this.position += BigInt(target.length);
    return target;
  }
  read(bytes) {
    return out(this.readInto(new Uint8Array(bytes)));
  }
  toBuffer(bytes = 32) {
    return this.read(bytes);
  }
}

export class Hasher {
  constructor(state) {
    this.state = state;
  }
  update(data, encoding) {
    native.update(this.state, typeof data === "string" ? Buffer.from(data, encoding) : bytes(data));
    return this;
  }
  digest(encoding, options) {
    if (typeof encoding === "object") [encoding, options] = [undefined, encoding];
    const buf = new Uint8Array(outLen(options?.length));
    native.finalize(this.state, buf, 0);
    return out(buf, encoding);
  }
  reader() {
    return new HashReader(this.state.slice(0));
  }
  dispose() {}
}

export const createHash = () => new Hasher(native.init(HASH));
export const createKeyed = (key) => new Hasher(stateFor({ key }));
export const createDeriveKey = (context) => new Hasher(stateFor({ context }));
export const hash = (input, options) => createHash().update(input).digest(options);
export const keyedHash = (key, input, options) => createKeyed(key).update(input).digest(options);
export const deriveKey = (context, material, options) =>
  createDeriveKey(context).update(material).digest(options);

// Many files at once
// ------------------

// Each file's BLAKE3 hash (a Uint8Array), opened, mapped or read in
// parallel, files not in the page cache streamed, every file's tree at once;
// or an Error for a file that could not be read. A pipe or device is read
// with the hasher instead.
export async function hashFiles(paths) {
  const rs = native.hashFiles(paths.map(String));
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
    for await (const chunk of createReadStream(p)) h.update(chunk);
    return h.digest();
  }));
}

export default blake3;
