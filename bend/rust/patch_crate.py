#!/usr/bin/env python3
"""Turns a copy of the official blake3 crate into turboblake, in place.

  patch_crate.py <crate dir> [package name]

Each patch must apply exactly once, so an upstream change that moves an
anchor stops the generator instead of producing a crate without its hook.
"""
import pathlib
import sys

HOOK = """    debug_assert!(input.len() > CHUNK_LEN);
    let mut cv_array = [0; MAX_SIMD_DEGREE_OR_2 * OUT_LEN];
    let mut num_cvs =
        compress_subtree_wide::<J>(input, &key, chunk_counter, flags, platform, &mut cv_array);
"""

ENGINE_BUILD = r'''
// turboblake: the Bend engine (csrc/engine.c, the C that Bend2 emits for
// bend/lib/engine.bend), compiled with clang's SLP vectorizer tuned as in
// bend/build.sh, and beside it the GPU backend (csrc/turboblake_gpu.c,
// ADR 0017), which loads Metal or CUDA at run time; TURBOBLAKE_NO_GPU=1
// leaves that out. Without clang the crate builds as upstream's, engine-less.
fn build_bend_engine() {
    println!("cargo::rerun-if-changed=csrc/engine.c");
    println!("cargo::rerun-if-changed=csrc/turboblake_gpu.c");
    println!("cargo::rerun-if-changed=csrc/turboblake_kernels.h");
    println!("cargo::rerun-if-env-changed=TURBOBLAKE_TARGET_CPU");
    println!("cargo::rerun-if-env-changed=TURBOBLAKE_NO_GPU");
    if env::var_os("CARGO_FEATURE_STD").is_none() || env::var_os("CARGO_FEATURE_PURE").is_some() {
        return;
    }
    let cc = env::var("CC").unwrap_or_else(|_| "clang".into());
    let version = std::process::Command::new(&cc)
        .arg("--version")
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default();
    if !version.contains("clang") {
        println!(
            "cargo::warning=turboblake: no clang (set CC to one): building without the Bend \
             engine, as the official blake3"
        );
        return;
    }
    let arch = env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let mut b = cc::Build::new();
    b.compiler(&cc)
        .file("csrc/engine.c")
        .std("c11")
        .opt_level(3)
        .define("BEND_EMBED", None)
        .define("main", "b3e_bend_main")
        .warnings(false)
        .flag("-w");
    // tuned for the machine that builds, unless cross-compiling
    // TURBOBLAKE_TARGET_CPU (e.g. "-march=x86-64-v3") sets a baseline instead,
    // for binaries that must run on every machine of their target.
    match env::var("TURBOBLAKE_TARGET_CPU") {
        Ok(cpu) if !cpu.is_empty() => {
            b.flag(&cpu);
        }
        _ if env::var("HOST") == env::var("TARGET") && env::var_os("TURBOBLAKE_PORTABLE").is_none() => {
            b.flag(if arch == "x86_64" { "-march=native" } else { "-mcpu=native" });
        }
        _ => {}
    }
    for f in [
        "-slp-max-reg-size=512",
        "-slp-recursion-max-depth=100000",
        "-slp-threshold=-20",
        "-inline-threshold=20000",
    ] {
        b.flag("-mllvm").flag(f);
    }
    let os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let gpu = (os == "macos" || os == "linux") && env::var_os("TURBOBLAKE_NO_GPU").is_none();
    if gpu {
        b.file("csrc/turboblake_gpu.c");
    }
    b.compile("turboblake_engine");
    println!("cargo::rustc-link-lib=pthread");
    println!("cargo::rustc-cfg=turboblake");
    if gpu {
        println!("cargo::rustc-cfg=turboblake_gpu");
        if os == "linux" {
            println!("cargo::rustc-link-lib=dl");
        }
    }
}
'''

PATCHES = {
    "Cargo.toml": [
        ('name = "blake3"\n', 'name = "{name}"\n'),
        ('description = "the BLAKE3 hash function"\n',
         'description = "the BLAKE3 hash function, with big inputs hashed on every core by a Bend2 '
         'engine: a drop-in for the blake3 crate"\n'),
        ('repository = "https://github.com/BLAKE3-team/BLAKE3"\n',
         'repository = "https://github.com/gunta/BLAKE3-bend"\n'
         'homepage = "https://gunta.github.io/BLAKE3-bend/"\n'),
        ('documentation = "https://docs.rs/blake3"\n',
         'documentation = "https://docs.rs/turboblake"\n'
         'links = "turboblake_engine"\n'),
        ('[features]\n', '[lib]\nname = "blake3"\n\n[features]\n'),
    ],
    "build.rs": [
        ('        "blake3_wasm32_simd",\n    ];',
         '        "blake3_wasm32_simd",\n        "turboblake",\n        "turboblake_gpu",\n    ];'),
        ('    if is_wasm32() && is_wasm32_simd() {\n        build_wasm32_simd();\n    }\n',
         '    if is_wasm32() && is_wasm32_simd() {\n        build_wasm32_simd();\n    }\n\n'
         '    if !is_wasm32() {\n        build_bend_engine();\n    }\n'),
        ('fn main() -> Result<(), Box<dyn std::error::Error>> {\n',
         ENGINE_BUILD.lstrip("\n") + '\nfn main() -> Result<(), Box<dyn std::error::Error>> {\n'),
    ],
    # The hook asks whether the caller wanted rayon: a span the engine must
    # copy loses to rayon on every core, so those stay upstream's.
    "src/join.rs": [
        ('pub trait Join {\n',
         'pub trait Join {\n'
         '    /// turboblake: true for `RayonJoin`, whose callers hash on every core\n'
         '    const PARALLEL: bool = false;\n\n'),
        ('impl Join for RayonJoin {\n',
         'impl Join for RayonJoin {\n    const PARALLEL: bool = true;\n\n'),
    ],
    "src/lib.rs": [
        ('mod io;\nmod join;\n',
         'mod io;\nmod join;\n\n#[cfg(feature = "std")]\npub mod bend;\n#[cfg(feature = "std")]\npub mod gpu;\n'),
        (HOOK, HOOK.replace("    let mut cv_array",
                            "    // turboblake: a big subtree goes to the Bend engine, on every core\n"
                            "    #[cfg(all(turboblake, feature = \"std\"))]\n"
                            "    if let Some(pair) = bend::subtree(input, key, chunk_counter, flags, platform, J::PARALLEL) {\n"
                            "        return pair;\n"
                            "    }\n"
                            "    let mut cv_array", 1)),
    ],
}


def main():
    crate = pathlib.Path(sys.argv[1])
    name = sys.argv[2] if len(sys.argv) > 2 else "turboblake"
    for rel, pairs in PATCHES.items():
        path = crate / rel
        s = path.read_text()
        for old, new in pairs:
            new = new.replace("{name}", name)
            if s.count(old) != 1:
                sys.exit(f"patch_crate.py: {path}: anchor not found once:\n{old}")
            s = s.replace(old, new)
        path.write_text(s)


if __name__ == "__main__":
    main()
