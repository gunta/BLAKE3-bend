#!/usr/bin/env python3
"""Turns a copy of the official b3sum into b3bend, in place.

  patch_b3sum.py <crate dir>

Each patch must apply exactly once (see patch_crate.py).
"""
import pathlib
import sys

LOOP = """        for path in &args.file_args {
            if args.check() {
                check_one_checkfile(path, &args, &mut files_failed)?;
            } else {
                // Errors encountered in hashing are tolerated and printed to
                // stderr. This allows e.g. `b3sum *` to print errors for
                // non-files and keep going. However, if we encounter any
                // errors we'll still return non-zero at the end.
                let result = hash_one_input(path, &args);
"""

PATCHES = {
    "Cargo.toml": [
        ('name = "b3sum"\n', 'name = "b3bend"\n'),
        ('description = "a command line implementation of the BLAKE3 hash function"\n',
         'description = "b3sum, with many files and big ones hashed at once by a Bend2 engine: '
         'a drop-in for b3sum"\n'),
        ('repository = "https://github.com/BLAKE3-team/BLAKE3"\n',
         'repository = "https://github.com/gunta/BLAKE3-bend"\n'
         'homepage = "https://gunta.github.io/BLAKE3-bend/"\n'),
        ('[features]\n',
         '# `cargo install b3bend --features replace` also installs it as `b3sum`.\n'
         '[[bin]]\nname = "b3bend"\npath = "src/main.rs"\n\n'
         '[[bin]]\nname = "b3sum"\npath = "src/replace.rs"\nrequired-features = ["replace"]\n\n'
         '[features]\nreplace = []\n'),
        ('blake3 = { version = "1.8.7", path = "..", features = ["mmap", "rayon"] }\n',
         'blake3 = { package = "blake3-bend", version = "1.8.7", path = "../rust/blake3-bend", '
         'features = ["mmap", "rayon"] }\n'),
    ],
    "src/main.rs": [
        ('#[cfg(test)]\nmod unit_tests;\n', '#[cfg(test)]\nmod unit_tests;\n\nmod fast;\n'),
        ('    let args = Args::parse()?;\n    let mut thread_pool_builder',
         '    let args = Args::parse()?;\n'
         '    // b3bend: --num-threads caps the Bend engine\'s threads too\n'
         '    if let Some(n) = args.num_threads() {\n'
         '        // SAFETY: no other thread runs yet.\n'
         '        unsafe { std::env::set_var("BLAKE3_BEND_THREADS", n.to_string()) };\n'
         '    }\n'
         '    let mut thread_pool_builder'),
        (LOOP, LOOP.replace("        for path in &args.file_args {",
                            "        let mut batch = fast::Batch::new(&args);\n"
                            "        for (i, path) in args.file_args.iter().enumerate() {")
                   .replace("                let result = hash_one_input(path, &args);",
                            "                let result = match batch.take(i) {\n"
                            "                    Some(hash) => fast::print(path, hash, &args),\n"
                            "                    None => hash_one_input(path, &args),\n"
                            "                };")),
    ],
    "tests/cli_tests.rs": [
        ('env!("CARGO_BIN_EXE_b3sum")', 'env!("CARGO_BIN_EXE_b3bend")'),
    ],
}


def main():
    crate = pathlib.Path(sys.argv[1])
    for rel, pairs in PATCHES.items():
        path = crate / rel
        s = path.read_text()
        for old, new in pairs:
            if s.count(old) != 1:
                sys.exit(f"patch_b3sum.py: {path}: anchor not found once:\n{old}")
            s = s.replace(old, new)
        path.write_text(s)


if __name__ == "__main__":
    main()
