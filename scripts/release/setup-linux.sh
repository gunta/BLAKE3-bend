#!/bin/sh
# Installs what a release build needs inside its Linux container:
# manylinux_2_28 (glibc 2.28, so the binaries run on RHEL 8, Debian 10,
# Ubuntu 20.04 and later) or Alpine (musl). Runs as root in the container.
#   setup-linux.sh cli|lib|npm
set -eu
what=$1
if command -v dnf >/dev/null; then
  dnf -y -q install clang >/dev/null
  case "$what" in
    npm) dnf -y -q module install nodejs:22/common >/dev/null ;;
  esac
elif command -v apk >/dev/null; then
  apk add -q clang build-base linux-headers curl python3 bash >/dev/null
  case "$what" in
    npm) apk add -q nodejs npm >/dev/null ;;
    lib) apk add -q cmake >/dev/null ;;
  esac
else
  echo "setup-linux.sh: neither dnf nor apk here" >&2
  exit 1
fi
if [ "$what" = cli ]; then
  # rustup's own installer, over TLS only, with no toolchain components beyond rustc and cargo
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs |
    sh -s -- -y -q --profile minimal --default-toolchain stable
fi
