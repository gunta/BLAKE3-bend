// turboblake: BLAKE3 on libturboblake for Node, Bun and Deno.
type Input = Uint8Array | ArrayBufferView | ArrayBuffer | string;

/** Options as @noble/hashes/blake3.js takes them. Use key or context, not both. */
export interface Blake3Opts {
  /** Output length in bytes (default 32). */
  dkLen?: number;
  /** 32-byte key: BLAKE3's keyed mode. */
  key?: Uint8Array;
  /** Context bytes: BLAKE3's key derivation mode. */
  context?: Uint8Array;
}

/** An incremental hasher, as @noble/hashes/blake3.js's _BLAKE3. */
export declare class BLAKE3 {
  constructor(opts?: Blake3Opts);
  readonly blockLen: 64;
  readonly canXOF: true;
  outputLen: number;
  update(data: Input): this;
  digest(): Uint8Array;
  digestInto(out: Uint8Array): Uint8Array;
  /** The next `bytes` of the extended output; calls continue where the last stopped. */
  xof(bytes: number): Uint8Array;
  xofInto(out: Uint8Array): Uint8Array;
  clone(): BLAKE3;
  destroy(): void;
}

/** BLAKE3, as @noble/hashes/blake3.js exports it. */
export declare const blake3: {
  (msg: Input, opts?: Blake3Opts): Uint8Array;
  create(opts?: Blake3Opts): BLAKE3;
  outputLen: 32;
  blockLen: 64;
  canXOF: true;
};
export default blake3;

/** Which engine runs: "native" (the addon over libturboblake) or "bend-js" (Bend's BLAKE3 emitted to JS). */
export declare const backend: "native" | "bend-js";

/** Extended output from a position, as the npm blake3 package's HashReader. */
export declare class HashReader {
  position: bigint;
  read(bytes: number): Buffer;
  readInto(target: Uint8Array): Uint8Array;
  toBuffer(bytes?: number): Buffer;
}

/** A hasher, as the npm blake3 package's. */
export declare class Hasher {
  update(data: Input, encoding?: BufferEncoding): this;
  digest(options?: { length?: number }): Buffer;
  digest(encoding: BufferEncoding, options?: { length?: number }): string;
  reader(): HashReader;
  dispose(): void;
}

export declare function createHash(): Hasher;
export declare function createKeyed(key: Uint8Array): Hasher;
export declare function createDeriveKey(context: string): Hasher;
export declare function hash(input: Input, options?: { length?: number }): Buffer;
export declare function keyedHash(key: Uint8Array, input: Input, options?: { length?: number }): Buffer;
export declare function deriveKey(context: string, material: Input, options?: { length?: number }): Buffer;

/** Each file's BLAKE3 hash, many files at once; an Error (with errno) for a file that could not be read. */
export declare function hashFiles(paths: string[]): Promise<(Uint8Array | (Error & { errno: number; path: string }))[]>;
