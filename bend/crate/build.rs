// Compiles csrc/b3sum.c, the single C file that Bend2 emits for
// bend/b3sum.bend (the Bend runtime, the BLAKE3 code and the I/O effects),
// with the flags bend/build.sh uses (ADR 0002): clang's SLP vectorizer packs
// compress8's eight lanes into SIMD registers. Bend's `main` is renamed so
// src/main.rs can hand it the command line.
use std::{env, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=csrc/b3sum.c");
    println!("cargo:rerun-if-env-changed=CC");
    let cc = env::var("CC").unwrap_or_else(|_| "clang".into());
    let version = Command::new(&cc)
        .arg("--version")
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default();
    if !version.contains("clang") {
        panic!(
            "b3sum-bend needs clang (Apple clang, or LLVM clang 19+): the Bend runtime uses \
             clang attributes and the build uses clang's -mllvm vectorizer flags. Set CC to a \
             clang if it is not the default."
        );
    }
    let arch = env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let host = env::var("HOST").unwrap_or_default();
    let target = env::var("TARGET").unwrap_or_default();
    let mut b = cc::Build::new();
    b.compiler(&cc)
        .file("csrc/b3sum.c")
        .std("c11")
        .opt_level(3)
        .define("main", "bend_b3sum_main")
        .warnings(false)
        .flag("-w");
    // cargo install builds on the machine that runs it: tune for it.
    if host == target {
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
    b.compile("bend_b3sum");
    println!("cargo:rustc-link-lib=pthread");
    println!("cargo:rustc-link-lib=m");
}
