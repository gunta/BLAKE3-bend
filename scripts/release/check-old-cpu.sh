#!/bin/sh
# An x86-64 binary built for x86-64-v3 must still run on a CPU without AVX2
# or AVX: its engine checks the CPU and leaves the hashing to the official
# C (ADR 0020). Runs BIN under qemu as a 2010 Westmere and a Core 2, and
# checks the hash against the native run. Needs qemu-user (qemu-x86_64).
#   check-old-cpu.sh BIN [ARGS...]   (BIN reads a file named by its last argument)
set -eu
bin=$1; shift
data=$(mktemp)
head -c 100000000 /dev/urandom > "$data"
want=$("$bin" "$@" "$data" | cut -c1-64)
for cpu in Westmere core2duo; do
  got=$(qemu-x86_64 -cpu "$cpu" "$bin" "$@" "$data" | cut -c1-64)
  [ "$got" = "$want" ] || { echo "check-old-cpu.sh: $cpu: '$got', want $want" >&2; exit 1; }
  echo "$cpu: $got"
done
rm -f "$data"
