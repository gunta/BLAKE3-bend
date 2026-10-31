---
name: migrate-to-turboblake-c
description: Move a C or C++ project from the official BLAKE3 C library (blake3.h, libblake3) to libturboblake, the drop-in that hashes big inputs on every CPU core with the same header, symbols and hasher layout. Use when the user asks to speed up BLAKE3 in C/C++, link libturboblake, or replace vendored blake3 sources.
---

# Migrate a C or C++ project to libturboblake

libturboblake is the official BLAKE3 C library with `blake3.h` unchanged (same symbols,
same `blake3_hasher` layout) plus one hook: big complete subtrees go to a Bend2 engine that
hashes them on every core. Programs keep `#include "blake3.h"` and relink; no source
changes. Outputs are byte-for-byte BLAKE3.

## 1. Find how BLAKE3 gets into the build

```bash
grep -rln --include=*.c --include=*.cc --include=*.cpp --include=*.h --include=*.hpp '#include *[<"]blake3.h[>"]' .
grep -rnE 'blake3|BLAKE3' CMakeLists.txt cmake/ meson.build Makefile* *.pc.in conanfile.* vcpkg.json 2>/dev/null
find . -name 'blake3*.c' -not -path './build/*' | head   # vendored sources?
```

It is one of: vendored `blake3*.c` files compiled in, `find_package(BLAKE3)` /
`BLAKE3::blake3` (CMake), `pkg-config libblake3`, `-lblake3`, or a package manager
(vcpkg `blake3`, Conan `blake3`).

## 2. Install libturboblake

```bash
brew install gunta/tap/libturboblake            # macOS, Linux
```

Or a `libturboblake-{{version}}-<target>.tar.gz` from
https://github.com/gunta/turboblake/releases/tag/turboblake-v{{version}} (macOS and Linux,
arm64 and x86-64; static and shared library, pkg-config file, CMake package), or from
source:

```bash
git clone --depth 1 --branch turboblake-v{{version}} https://github.com/gunta/turboblake
cmake -S turboblake/bend/lib -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang
cmake --build build && cmake --install build --prefix /usr/local
```

Headers install to `include/turboblake/` (never over an existing `blake3.h`).

## 3. Point the build at it

- **CMake**: `find_package(BLAKE3)` + `BLAKE3::blake3` becomes
  ```cmake
  find_package(turboblake REQUIRED)
  target_link_libraries(app PRIVATE turboblake::turboblake)
  ```
  The target puts `include/turboblake` on the include path, so `#include "blake3.h"` resolves.
- **pkg-config**: `libblake3` becomes `libturboblake`:
  `cc app.c $(pkg-config --cflags --libs libturboblake) -o app` (add `--static` for the
  static library: it pulls in `-lpthread -lm` and `-ldl`).
- **Makefile / plain flags**: `-lblake3` becomes `-I<prefix>/include/turboblake -lturboblake -lpthread -lm`.
- **Vendored sources**: delete the vendored `blake3*.c`/`.S`/`.asm` from the build (keep
  `blake3.h` only if the include path needs it) and link libturboblake instead.
- **Meson**: `dependency('libturboblake')` (pkg-config).

C++ is the same: `blake3.h` has its own `extern "C"`.

## 4. Verify

```c
#include "blake3.h"
#include <stdio.h>
#include <string.h>
int main(void) {
  uint8_t in[1024], out[32]; char hex[65];
  for (int i = 0; i < 1024; i++) in[i] = (uint8_t)(i % 251);
  blake3_hasher h; blake3_hasher_init(&h);
  blake3_hasher_update(&h, in, sizeof in);
  blake3_hasher_finalize(&h, out, 32);
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", out[i]);
  return strcmp(hex, "42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7") != 0;
}
```

Check the binary links the new library (`otool -L` on macOS, `ldd` on Linux, for the shared
one) and run the project's tests. `TURBOBLAKE_TRACE=1 ./app` prints the engine's calibration
and jobs to stderr once an update is big (a few MiB). `turboblake.h` adds
`turboblake_running()` (1 once the engine started) and the GPU calls, if wanted.

## Know before you ship

- The engine needs clang on a POSIX system. Built elsewhere (Windows, gcc), the library is
  the official C alone: same results, upstream speed.
- `-DTURBOBLAKE_TARGET_CPU=native` tunes the engine for the build machine; the default is
  each platform's release baseline and checks the CPU at run time.
- The engine starts a thread on the first big update; a forked child hashes with the
  official code.
- It pays off from about 256 KiB per update; small updates are upstream's code path.
- Run-time switches: `TURBOBLAKE=0` (engine off), `TURBOBLAKE_THREADS=<n>`,
  `TURBOBLAKE_MIN=<bytes>`, `TURBOBLAKE_GPU=0`.
- Rolling back: link `libblake3` again; no source changed.

License: CC0-1.0 OR Apache-2.0 OR Apache-2.0 WITH LLVM-exception, as BLAKE3. The engine
contains the Bend2 runtime, Apache-2.0.
Docs: https://gunta.github.io/turboblake/install/c/
