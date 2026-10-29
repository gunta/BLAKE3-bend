#!/bin/sh
# Installs the packed npm package (TGZ) into an empty project, as a user
# would, and checks it runs on its prebuilt addon, not the JavaScript
# fallback, with the right hashes; under Bun too when bun is there.
#   smoke-npm.sh TGZ
set -eu
tgz=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
app=$(mktemp -d)
cd "$app"
npm init -y >/dev/null
npm install --no-audit --no-fund --loglevel=error "$tgz"
cat > check.mjs <<'JS'
import { blake3, hash, backend } from "turboblake";
const hex = (b) => Buffer.from(b).toString("hex");
const want = "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85";
const abc = new TextEncoder().encode("abc");
if (backend !== "native") throw new Error(`backend is ${backend}, not native`);
if (hex(blake3(abc)) !== want || hex(hash(abc)) !== want) throw new Error("wrong hash");
const big = new Uint8Array(64 << 20).map((_, i) => i % 251);
console.log(`${process.platform}-${process.arch}: ${backend}, 64 MiB ${hex(blake3(big)).slice(0, 16)}...`);
JS
node check.mjs
if command -v bun >/dev/null; then bun check.mjs; fi
