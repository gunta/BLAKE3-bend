#!/bin/sh
# Builds the npm package's addon for one platform (bend/node/prebuilt.mjs
# lists them), runs the package's tests on it, and writes it to
# OUT/prebuilds/<platform>/turboblake.node. On Linux it also checks the
# addon asks for no glibc newer than manylinux_2_28's.
#   build-npm.sh PLATFORM OUT
set -eu
. "$(dirname "$0")/common.sh"
platform=$1
out=$(mkdir -p "$2" && cd "$2" && pwd)
cd "$root/bend/node"
here=$(node prebuilt.mjs name)
[ "$here" = "$platform" ] || die "this machine is $here, not $platform"
TURBOBLAKE_TARGET_CPU=$(node --input-type=module -e \
  "import { platforms } from './prebuilt.mjs'; console.log(platforms[process.argv[1]])" "$platform")
export TURBOBLAKE_TARGET_CPU
npm install --ignore-scripts --no-audit --no-fund --loglevel=error
node build.mjs
node test/test.mjs
case "$platform" in
  linux-*-gnu)
    newest=$(objdump -T build/turboblake.node | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1)
    say "glibc: needs $newest"
    [ "$(printf '%s\nGLIBC_2.28\n' "$newest" | sort -V | tail -1)" = GLIBC_2.28 ] || die "needs $newest"
    ;;
esac
node prebuilt.mjs pack "$out"
