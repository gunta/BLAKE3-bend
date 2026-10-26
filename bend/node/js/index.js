// turboblake for JavaScript alone (browsers, workers, Deno Deploy): the faces of
// ../api.js over Bend's own BLAKE3, emitted to JS (engine.js).
import { faces } from "../api.js";
import { engine } from "./engine.js";

export const { blake3, BLAKE3, HashReader, Hasher, createHash, createKeyed, createDeriveKey, hash,
  keyedHash, deriveKey } = faces(engine);
export const backend = engine.name;
export default blake3;
