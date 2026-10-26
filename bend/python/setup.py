"""Builds blake3._blake3: blake3module.c on libblake3-bend (bend/lib).

The C comes from bend/lib/csrc (copied in, for an sdist): the official C
library with its subtree hook, the glue, and the engine (the C that Bend2
emits). Only the engine needs clang, for its vectorizer flags; without
clang the module builds on the official C alone, and says so.

Environment: BLAKE3_BEND_PORTABLE=1 builds for the baseline CPU instead of
this one; BLAKE3_BEND_NO_ENGINE=1 leaves the engine out.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import setuptools
from setuptools.command.build_ext import build_ext

HERE = Path(__file__).resolve().parent
CSRC = HERE / "csrc"
VERSION = "1.8.7"

# in the repository, always the current C; in an sdist, the copy it ships
if (HERE.parent / "lib" / "csrc" / "engine.c").exists():
    shutil.copytree(HERE.parent / "lib" / "csrc", CSRC, dirs_exist_ok=True)

MACHINE = platform.machine().lower()
X86_64 = MACHINE in ("x86_64", "amd64") and sys.maxsize.bit_length() == 63
AARCH64 = MACHINE in ("aarch64", "arm64")
WINDOWS = sys.platform.startswith("win32")
# the engine's flags are bend/build.sh's (ADR 0002)
SLP = ["-mllvm", "-slp-max-reg-size=512", "-mllvm", "-slp-recursion-max-depth=100000",
       "-mllvm", "-slp-threshold=-20", "-mllvm", "-inline-threshold=20000"]


def find_clang():
    for cc in (os.environ.get("CC"), "clang"):
        if not cc:
            continue
        try:
            out = subprocess.run([cc, "--version"], capture_output=True, text=True).stdout
        except OSError:
            continue
        if "clang" in out:
            return cc
    return None


class BuildExt(build_ext):
    def build_extension(self, ext):
        tmp = Path(self.build_temp)
        tmp.mkdir(parents=True, exist_ok=True)
        cc = None if os.environ.get("BLAKE3_BEND_NO_ENGINE") or WINDOWS else find_clang()
        if cc:
            cpu = [] if os.environ.get("BLAKE3_BEND_PORTABLE") else (
                ["-march=native"] if X86_64 else ["-mcpu=native"])
            obj = tmp / "engine.o"
            cmd = [cc, "-x", "c", "-std=c11", "-O3", *cpu, "-fPIC", "-w", "-DBEND_EMBED",
                   "-Dmain=b3e_bend_main", *SLP, "-c", str(CSRC / "engine.c"), "-o", str(obj)]
            print(" ".join(cmd))
            subprocess.run(cmd, check=True)
            ext.extra_objects.append(str(obj))
            ext.sources.append("csrc/blake3_bend.c")
            ext.define_macros.append(("BLAKE3_BEND", "1"))
        else:
            print("turboblake: no clang (set CC to one), building without the Bend engine")
        if X86_64 and not WINDOWS:
            # the C compiler assembles .S files given as objects
            ext.extra_objects += [f"csrc/blake3_{s}_x86-64_unix.S"
                                  for s in ("sse2", "sse41", "avx2", "avx512")]
        elif AARCH64:
            ext.sources.append("csrc/blake3_neon.c")
            ext.define_macros.append(("BLAKE3_USE_NEON", "1"))
        else:
            ext.define_macros += [("BLAKE3_NO_SSE2", "1"), ("BLAKE3_NO_SSE41", "1"),
                                  ("BLAKE3_NO_AVX2", "1"), ("BLAKE3_NO_AVX512", "1")]
        super().build_extension(ext)


setuptools.setup(
    ext_modules=[
        setuptools.Extension(
            "blake3._blake3",
            sources=["blake3module.c", "csrc/blake3.c", "csrc/blake3_dispatch.c",
                     "csrc/blake3_portable.c"],
            include_dirs=["csrc"],
            define_macros=[
                ("SETUP_PY_VERSION", f'"{VERSION}"'),
                ("SETUP_PY_DESCRIPTION", '"BLAKE3 on libblake3-bend"'),
            ],
            extra_compile_args=[] if WINDOWS else ["-O3", "-std=c11"],
            libraries=[] if WINDOWS else ["pthread", "m"],
        )
    ],
    cmdclass={"build_ext": BuildExt},
)
