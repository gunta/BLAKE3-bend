# Shared by the release scripts (sourced): where things are, and each
# target's settings. A target is a Rust target triple; every prebuilt piece
# (the command line, libturboblake, the npm addon, the wheels) is built for
# the same baseline CPU per target, and the engine checks the CPU before it
# runs (ADR 0020).
root=$(cd "$(dirname "$0")/../.." && pwd)
version=$(cat "$root/bend/VERSION")

# The engine's CPU flags for a target ("" where there is no engine).
engine_cpu() {
  case "$1" in
    aarch64-apple-darwin) echo "-mcpu=apple-m1" ;;
    x86_64-*-windows-*|aarch64-*-windows-*) echo "" ;;
    x86_64-*) echo "-march=x86-64-v3" ;;
    aarch64-*) echo "-mcpu=generic" ;;
    *) echo "" ;;
  esac
}

# The command's file name on a target.
exe() {
  case "$1" in *-windows-*) echo "turboblake.exe" ;; *) echo "turboblake" ;; esac
}

say() { printf '%s\n' "$*" >&2; }
die() { say "error: $*"; exit 1; }
