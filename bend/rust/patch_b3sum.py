#!/usr/bin/env python3
"""Turns a copy of the official b3sum into turboblake, in place.

  patch_b3sum.py <crate dir>

Each patch must apply exactly once (see patch_crate.py); each REPLACE_ALL
pair must appear at least once.
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

POOL = """    let args = Args::parse()?;
    let mut thread_pool_builder = rayon_core::ThreadPoolBuilder::new();
    if let Some(num_threads) = args.num_threads() {
        thread_pool_builder = thread_pool_builder.num_threads(num_threads);
    }
    let thread_pool = thread_pool_builder.build()?;
    thread_pool.install(|| {
"""

CHECK_LOOP = """    let mut line = String::new();
    loop {
        line.clear();
        let n = bufreader.read_line(&mut line)?;
        if n == 0 {
            return Ok(());
        }
        // check_one_line() prints errors and turns them into a success=false
        // return, so it doesn't return a Result.
        let success = check_one_line(&line, args);
        if !success {
            // We use `files_failed > 0` to indicate a mismatch, so it's important for correctness
            // that it's impossible for this counter to overflow.
            *files_failed = files_failed.saturating_add(1);
        }
    }
}
"""

CHECK_BATCHED = """    loop {
        // turboblake: a batch of lines at a time, their files hashed at once
        let lines = fast::check_batch(&mut bufreader, args)?;
        if lines.is_empty() {
            return Ok(());
        }
        for line in &lines {
            // check_one_line() prints errors and turns them into a success=false
            // return, so it doesn't return a Result.
            let success = check_one_line(line, args);
            if !success {
                // We use `files_failed > 0` to indicate a mismatch, so it's important for correctness
                // that it's impossible for this counter to overflow.
                *files_failed = files_failed.saturating_add(1);
            }
        }
    }
}
"""

CHECK_HASH = """    let found_hash: blake3::Hash;
    match hash_path(args, &file_path) {
        Ok(mut output) => {
            let mut found_hash_bytes = [0; blake3::OUT_LEN];
            output.fill(&mut found_hash_bytes);
            found_hash = found_hash_bytes.into();
        }
"""

PATCHES = {
    "Cargo.toml": [
        ('name = "b3sum"\n', 'name = "turboblake"\n'),
        ('description = "a command line implementation of the BLAKE3 hash function"\n',
         'description = "BLAKE3, turbocharged: the official b3sum with many files and big ones '
         'hashed at once by a Bend2 engine, a drop-in for b3sum and sha256sum"\n'),
        ('repository = "https://github.com/BLAKE3-team/BLAKE3"\n',
         'repository = "https://github.com/gunta/BLAKE3-bend"\n'
         'homepage = "https://gunta.github.io/BLAKE3-bend/"\n'),
        ('[features]\n',
         '# `cargo install turboblake --features replace` also installs it as `b3sum`.\n'
         '[[bin]]\nname = "turboblake"\npath = "src/main.rs"\n\n'
         '[[bin]]\nname = "b3sum"\npath = "src/replace.rs"\nrequired-features = ["replace"]\n\n'
         '[features]\nreplace = []\n'),
        ('blake3 = { version = "1.8.7", path = "..", features = ["mmap", "rayon"] }\n',
         'blake3 = { package = "blake3-bend", version = "1.8.7", path = "../rust/blake3-bend", '
         'features = ["mmap", "rayon"] }\n'),
        ('[dev-dependencies]\n',
         '# `cargo binstall turboblake` downloads the release archives instead of building.\n'
         '[package.metadata.binstall]\n'
         'pkg-url = "{ repo }/releases/download/turboblake-v{ version }/turboblake-{ version }-{ target }.tar.gz"\n'
         'bin-dir = "turboblake-{ version }-{ target }/{ bin }{ binary-ext }"\n'
         'pkg-fmt = "tgz"\n\n'
         '[dev-dependencies]\n'),
    ],
    "src/main.rs": [
        ('#[cfg(test)]\nmod unit_tests;\n', '#[cfg(test)]\nmod unit_tests;\n\nmod fast;\n'),
        ('const NAME: &str = "b3sum";\n',
         '// turboblake: messages start with the binary\'s name, "turboblake", or "b3sum"\n'
         '// for the `replace` install, which stays byte-identical to upstream.\n'
         'const NAME: &str = env!("CARGO_BIN_NAME");\n'),
        (POOL,
         '    let args = Args::parse()?;\n'
         '    // turboblake: --num-threads caps the Bend engine\'s threads too, and\n'
         '    // blake3-bend\'s subtree hook stays off: upstream\'s paths here stay\n'
         '    // upstream\'s, and fast.rs gives the engine what it wins on (a file the\n'
         '    // hook took would pay the engine\'s start). SAFETY: no other thread runs.\n'
         '    if let Some(n) = args.num_threads() {\n'
         '        unsafe { std::env::set_var("BLAKE3_BEND_THREADS", n.to_string()) };\n'
         '    }\n'
         '    if std::env::var_os("BLAKE3_BEND_MIN").is_none() {\n'
         '        unsafe { std::env::set_var("BLAKE3_BEND_MIN", usize::MAX.to_string()) };\n'
         '    }\n'
         '    // turboblake: rayon\'s threads start when a file first needs them\n'
         '    fast::pool(args.num_threads(), || {\n'),
        ('        std::process::exit(if files_failed > 0 { 1 } else { 0 });\n    })\n}\n',
         '        std::process::exit(if files_failed > 0 { 1 } else { 0 });\n    })?\n}\n'),
        (CHECK_LOOP, CHECK_BATCHED),
        (CHECK_HASH, CHECK_HASH.replace(
            '    match hash_path(args, &file_path) {\n'
            '        Ok(mut output) => {\n'
            '            let mut found_hash_bytes = [0; blake3::OUT_LEN];\n'
            '            output.fill(&mut found_hash_bytes);\n'
            '            found_hash = found_hash_bytes.into();\n'
            '        }\n',
            '    // turboblake: the engine may have hashed it with its batch (fast.rs)\n'
            '    match fast::checked(&file_path).unwrap_or_else(|| {\n'
            '        hash_path(args, &file_path).map(|mut output| {\n'
            '            let mut found_hash_bytes = [0; blake3::OUT_LEN];\n'
            '            output.fill(&mut found_hash_bytes);\n'
            '            found_hash_bytes.into()\n'
            '        })\n'
            '    }) {\n'
            '        Ok(hash) => found_hash = hash,\n')),
        ('        hasher.update_reader(io::stdin().lock())?;\n',
         '        // (turboblake: big blocks, read while the one before hashes)\n'
         '        fast::update_stdin(&mut hasher)?;\n'),
        ('        hasher.update_reader(File::open(path)?)?;\n',
         '        fast::update_file(&mut hasher, File::open(path)?)?;\n'),
        ('        hasher.update_mmap_rayon(path)?;\n',
         '        // (turboblake: on one thread if it is small)\n'
         '        fast::update_path(&mut hasher, path)?;\n'),
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
        ('env!("CARGO_BIN_EXE_b3sum")', 'env!("CARGO_BIN_EXE_turboblake")'),
    ],
}

# Upstream's CLI tests expect stderr lines from a binary called b3sum.
REPLACE_ALL = {
    "tests/cli_tests.rs": [("b3sum: ", "turboblake: ")],
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
    for rel, pairs in REPLACE_ALL.items():
        path = crate / rel
        s = path.read_text()
        for old, new in pairs:
            if old not in s:
                sys.exit(f"patch_b3sum.py: {path}: {old!r} not found")
            s = s.replace(old, new)
        path.write_text(s)


if __name__ == "__main__":
    main()
