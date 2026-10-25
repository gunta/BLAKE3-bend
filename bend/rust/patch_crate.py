#!/usr/bin/env python3
"""Turns a copy of the official blake3 crate into blake3-bend, in place.

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
// blake3-bend: the Bend engine (csrc/engine.c, the C that Bend2 emits for
// bend/lib/engine.bend), compiled with clang's SLP vectorizer tuned as in
// bend/build.sh. Without clang the crate builds as upstream's, engine-less.
fn build_bend_engine() {
    println!("cargo::rerun-if-changed=csrc/engine.c");
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
            "cargo::warning=blake3-bend: no clang (set CC to one): building without the Bend \
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
    if env::var("HOST") == env::var("TARGET") && env::var_os("BLAKE3_BEND_PORTABLE").is_none() {
        b.flag(if arch == "x86_64" { "-march=native" } else { "-mcpu=native" });
    }
    for f in [
        "-slp-max-reg-size=512",
        "-slp-recursion-max-depth=100000",
        "-slp-threshold=-20",
        "-inline-threshold=20000",
    ] {
        b.flag("-mllvm").flag(f);
    }
    b.compile("blake3_bend_engine");
    println!("cargo::rustc-link-lib=pthread");
    println!("cargo::rustc-cfg=blake3_bend");
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
         'documentation = "https://docs.rs/blake3-bend"\n'
         'links = "blake3_bend_engine"\n'),
        ('[features]\n', '[lib]\nname = "blake3"\n\n[features]\n'),
    ],
    "build.rs": [
        ('        "blake3_wasm32_simd",\n    ];', '        "blake3_wasm32_simd",\n        "blake3_bend",\n    ];'),
        ('    if is_wasm32() && is_wasm32_simd() {\n        build_wasm32_simd();\n    }\n',
         '    if is_wasm32() && is_wasm32_simd() {\n        build_wasm32_simd();\n    }\n\n'
         '    if !is_wasm32() {\n        build_bend_engine();\n    }\n'),
        ('fn main() -> Result<(), Box<dyn std::error::Error>> {\n',
         ENGINE_BUILD.lstrip("\n") + '\nfn main() -> Result<(), Box<dyn std::error::Error>> {\n'),
    ],
    "src/lib.rs": [
        ('mod io;\nmod join;\n',
         'mod io;\nmod join;\n\n#[cfg(feature = "std")]\npub mod bend;\n'),
        (HOOK, HOOK.replace("    let mut cv_array",
                            "    // blake3-bend: a big subtree goes to the Bend engine, on every core\n"
                            "    #[cfg(all(blake3_bend, feature = \"std\"))]\n"
                            "    if let Some(pair) = bend::subtree(input, key, chunk_counter, flags, platform) {\n"
                            "        return pair;\n"
                            "    }\n"
                            "    let mut cv_array", 1)),
    ],
}


def main():
    crate = pathlib.Path(sys.argv[1])
    name = sys.argv[2] if len(sys.argv) > 2 else "blake3-bend"
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
