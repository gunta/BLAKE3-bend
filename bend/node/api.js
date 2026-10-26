// turboblake's two drop-in faces, over an engine (the native addon, or the
// pure-JS one in js/engine.js):
//   - blake3(msg, { dkLen, key, context }) and blake3.create(opts), as
//     @noble/hashes/blake3.js exports them;
//   - hash, keyedHash, deriveKey, createHash, createKeyed, createDeriveKey,
//     as the blake3 package on npm exports them.
// An engine: init(mode, keyOrContext) -> state, update(state, bytes),
// finalize(state, out, seek), clone(state), hash(bytes, out).
export function faces(engine) {
  const HASH = 0, KEYED = 1, DERIVE = 2;
  const enc = new TextEncoder();

  function bytes(data, what = "input") {
    if (data instanceof Uint8Array) return data;
    if (typeof data === "string") return enc.encode(data);
    if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    if (data instanceof ArrayBuffer) return new Uint8Array(data);
    throw new TypeError(`turboblake: ${what} must be a Uint8Array, a TypedArray, an ArrayBuffer or a string`);
  }

  function stateFor(opts = {}) {
    if (opts.key !== undefined && opts.context !== undefined) {
      throw new Error("turboblake: use either key or context, not both");
    }
    if (opts.key !== undefined) return engine.init(KEYED, bytes(opts.key, "key"));
    if (opts.context !== undefined) return engine.init(DERIVE, bytes(opts.context, "context"));
    return engine.init(HASH);
  }

  function outLen(n, fallback = 32) {
    if (n === undefined) return fallback;
    if (!Number.isSafeInteger(n) || n < 0) throw new RangeError("turboblake: bad output length");
    return n;
  }

  // @noble/hashes
  // -------------

  class BLAKE3 {
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
      if (this.destroyed) throw new Error("turboblake: hash instance has been destroyed");
      if (this.finished) throw new Error("turboblake: digest() has already been called");
      engine.update(this.state, bytes(data));
      return this;
    }
    digestInto(out) {
      if (this.finished) throw new Error("turboblake: digest() has already been called");
      this.finished = true;
      engine.finalize(this.state, out, 0);
      return out;
    }
    digest() {
      return this.digestInto(new Uint8Array(this.outputLen));
    }
    xofInto(out) {
      if (this.destroyed) throw new Error("turboblake: hash instance has been destroyed");
      if (this.finished && this.posOut === 0) throw new Error("turboblake: XOF is not possible after digest()");
      this.finished = true;
      engine.finalize(this.state, out, this.posOut);
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
      const state = engine.clone(this.state);
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
      if (this.state instanceof ArrayBuffer) new Uint8Array(this.state).fill(0);
    }
  }

  const blake3 = Object.assign(
    (msg, opts) => {
      if (opts === undefined || (opts.key === undefined && opts.context === undefined)) {
        const out = new Uint8Array(outLen(opts?.dkLen));
        engine.hash(bytes(msg), out);
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
    if (typeof Buffer === "undefined") {
      if (encoding === undefined) return buf;
      if (encoding === "hex") return Array.from(buf, (x) => x.toString(16).padStart(2, "0")).join("");
      throw new Error("turboblake: only hex output without Buffer");
    }
    const b = Buffer.from(buf.buffer, buf.byteOffset, buf.byteLength);
    return encoding === undefined ? b : b.toString(encoding);
  }

  class HashReader {
    constructor(state) {
      this.state = state;
      this.position = 0n;
    }
    readInto(target) {
      engine.finalize(this.state, target, Number(this.position));
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

  class Hasher {
    constructor(state) {
      this.state = state;
    }
    update(data, encoding) {
      engine.update(this.state, typeof data === "string" && encoding !== undefined && typeof Buffer !== "undefined"
        ? Buffer.from(data, encoding) : bytes(data));
      return this;
    }
    digest(encoding, options) {
      if (typeof encoding === "object") [encoding, options] = [undefined, encoding];
      const buf = new Uint8Array(outLen(options?.length));
      engine.finalize(this.state, buf, 0);
      return out(buf, encoding);
    }
    reader() {
      return new HashReader(engine.clone(this.state));
    }
    dispose() {}
  }

  const createHash = () => new Hasher(engine.init(HASH));
  const createKeyed = (key) => new Hasher(stateFor({ key }));
  const createDeriveKey = (context) => new Hasher(stateFor({ context }));
  const hash = (input, options) => createHash().update(input).digest(options);
  const keyedHash = (key, input, options) => createKeyed(key).update(input).digest(options);
  const deriveKey = (context, material, options) =>
    createDeriveKey(context).update(material).digest(options);


  return { blake3, BLAKE3, HashReader, Hasher, createHash, createKeyed, createDeriveKey, hash,
    keyedHash, deriveKey };
}
