// b3bend's engine for JavaScript alone (browsers, workers, or Node with no
// native addon): BLAKE3 as Bend wrote it, emitted to JS (blake3.mjs, from
// bend/js/blake3.bend), driven here by the official incremental algorithm.
// Every compression runs in Bend's code: the spans of whole subtrees, the
// parents, the roots and the extended output; this file keeps the bytes
// not yet hashed and the stack of subtree CVs, as the official Hasher does.
import B from "./blake3.mjs";

const CHUNK = 1024;
const FLUSH = 1 << 21; // bytes kept before whole subtrees are hashed
const LE = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
const KEYED = 16, DERIVE_CONTEXT = 32, DERIVE_MATERIAL = 64;
const IV = B.IV();

// A span's bytes as Bend reads them: little-endian words, zeros to the end
// of the last 64-byte block.
function words(bytes) {
  const w = new Uint32Array(Math.max(16, Math.ceil(bytes.length / 64) * 16));
  if (LE) {
    new Uint8Array(w.buffer).set(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) w[i >> 2] |= bytes[i] << (8 * (i & 3));
  }
  return w;
}

function cvOf(b) {
  const w = [];
  for (let i = 0; i < 8; i += 1) {
    w.push((b[4 * i] | (b[4 * i + 1] << 8) | (b[4 * i + 2] << 16) | (b[4 * i + 3] << 24)) >>> 0);
  }
  return { $: "CV", h0: w[0], h1: w[1], h2: w[2], h3: w[3], h4: w[4], h5: w[5], h6: w[6], h7: w[7] };
}

function putCV(cv, out, at) {
  for (let i = 0; i < 8; i += 1) {
    const x = cv[`h${i}`];
    out[at + 4 * i] = x & 255;
    out[at + 4 * i + 1] = (x >>> 8) & 255;
    out[at + 4 * i + 2] = (x >>> 16) & 255;
    out[at + 4 * i + 3] = (x >>> 24) & 255;
  }
}

const popcount = (n) => {
  let c = 0;
  for (; n > 0; n = Math.floor(n / 2)) c += n % 2;
  return c;
};

class State {
  constructor(key, kf) {
    this.key = key;
    this.kf = kf;
    this.stack = [];
    this.chunks = 0;
    this.buf = new Uint8Array(FLUSH + CHUNK);
    this.len = 0;
  }
  clone() {
    const s = new State(this.key, this.kf);
    s.stack = this.stack.slice();
    s.chunks = this.chunks;
    s.buf = this.buf.slice();
    s.len = this.len;
    return s;
  }
}

// Merges the stack down to one CV per set bit of the chunk count, as the
// official hasher_merge_cv_stack does before each push.
function merge(stack, chunks, key, kf) {
  while (stack.length > popcount(chunks)) {
    const r = stack.pop();
    const l = stack.pop();
    stack.push(B.parent(l, r, key, kf));
  }
}

// The largest whole subtree that starts at chunk `chunks` and fits in
// `avail` bytes, in chunks.
function subtree(chunks, avail) {
  let s = 1;
  while (s * 2 * CHUNK <= avail) s *= 2;
  while (chunks % s !== 0) s /= 2;
  return s;
}

// Hashes whole subtrees from bytes[0..] into the stack, leaving at least
// `keep` bytes; answers how many bytes it took.
function consume(st, stack, bytes, len, keep, chunksAt) {
  let off = 0, chunks = chunksAt;
  while (len - off - keep >= CHUNK) {
    const s = subtree(chunks, len - off - keep);
    const cv = B.span(words(bytes.subarray(off, off + s * CHUNK)), chunks, s, CHUNK, 0, st.key, st.kf);
    merge(stack, chunks, st.key, st.kf);
    stack.push(cv);
    chunks += s;
    off += s * CHUNK;
  }
  return [off, chunks];
}

function root(st) {
  const stack = st.stack.slice();
  const [off, chunks] = consume(st, stack, st.buf, st.len, 1, st.chunks);
  const tail = st.buf.subarray(off, st.len);
  merge(stack, chunks, st.key, st.kf);
  if (stack.length === 0) return B["chunk.root"](words(tail), chunks, tail.length, st.key, st.kf);
  let cur = B.span(words(tail), chunks, 1, tail.length, 0, st.key, st.kf);
  while (stack.length > 1) cur = B.parent(stack.pop(), cur, st.key, st.kf);
  return B["parent.root"](stack.pop(), cur, st.key, st.kf);
}

function finalize(st, out, seek = 0) {
  const r = root(st);
  let pos = seek, done = 0;
  const block = new Uint8Array(64);
  while (done < out.length) {
    const t = Math.floor(pos / 64);
    const two = B["root.out"](r, t % 2 ** 32, Math.floor(t / 2 ** 32));
    putCV(two.fst, block, 0);
    putCV(two.snd, block, 32);
    const from = pos % 64, n = Math.min(64 - from, out.length - done);
    out.set(block.subarray(from, from + n), done);
    done += n;
    pos += n;
  }
}

function update(st, bytes) {
  for (let off = 0; off < bytes.length;) {
    const n = Math.min(bytes.length - off, st.buf.length - st.len);
    st.buf.set(bytes.subarray(off, off + n), st.len);
    st.len += n;
    off += n;
    if (st.len === st.buf.length) {
      // hash whole subtrees, keeping a byte: the end is still to come
      const [took, chunks] = consume(st, st.stack, st.buf, st.len, 1, st.chunks);
      st.buf.copyWithin(0, took, st.len);
      st.len -= took;
      st.chunks = chunks;
    }
  }
}

export const engine = {
  name: "bend-js",
  // mode 0 hash, 1 keyed (32-byte key), 2 derive-key (context bytes)
  init(mode, k) {
    if (mode === 1) {
      if (k.length !== 32) throw new RangeError("b3bend: a key is 32 bytes");
      return new State(cvOf(k), KEYED);
    }
    if (mode === 2) {
      const c = new State(IV, DERIVE_CONTEXT);
      update(c, k);
      const ck = new Uint8Array(32);
      finalize(c, ck);
      return new State(cvOf(ck), DERIVE_MATERIAL);
    }
    return new State(IV, 0);
  },
  update,
  finalize,
  clone: (st) => st.clone(),
  hash(bytes, out) {
    if (out.length === 32 && bytes.length <= FLUSH) {
      putCV(B.hash(words(bytes), bytes.length), out, 0);
      return;
    }
    const st = new State(IV, 0);
    update(st, bytes);
    finalize(st, out);
  },
};
