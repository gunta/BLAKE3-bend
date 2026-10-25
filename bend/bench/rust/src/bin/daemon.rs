// Daemon benchmark, the Rust side of bench/daemon.bend: start once, then
// hash the same files round after round, timing each round in-process.
// Each round opens and maps (or reads) every file again and drops it after,
// as a sync service would. Prints "us <round microseconds> fold <xor>".
//
// mode "par": rayon over the files, each file update_mmap_rayon (mmap for
// files over 16 KiB, as b3sum does; a read below that). The strongest
// baseline we could write with the official crate.
// mode "seq": one file at a time, as b3sum does.
//
// usage: daemon <rounds> <par|seq> FILE...
use rayon::prelude::*;
use std::time::Instant;

fn hash_file(path: &str) -> blake3::Hash {
    let mut h = blake3::Hasher::new();
    let len = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    if len > 16 * 1024 {
        h.update_mmap_rayon(path).expect("mmap");
    } else {
        h.update(&std::fs::read(path).expect("read"));
    }
    h.finalize()
}

fn fold(h: &blake3::Hash) -> u32 {
    h.as_bytes()
        .chunks(4)
        .fold(0u32, |x, w| x ^ u32::from_le_bytes([w[0], w[1], w[2], w[3]]))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let rounds: usize = args[1].parse().unwrap();
    let par = args[2] == "par";
    let paths = &args[3..];
    for _ in 0..rounds {
        let t = Instant::now();
        let x = if par {
            paths.par_iter().map(|p| fold(&hash_file(p))).reduce(|| 0, |a, b| a ^ b)
        } else {
            paths.iter().map(|p| fold(&hash_file(p))).fold(0, |a, b| a ^ b)
        };
        println!("us {} fold {}", t.elapsed().as_micros(), x);
    }
}
