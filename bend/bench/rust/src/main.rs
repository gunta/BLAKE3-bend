// Reference in-memory benchmark: the official blake3 crate (NEON + rayon)
// over the same data bend/bench/mem.bend hashes, word j = j*2654435761+12345.
// usage: b3ref <d> <reps> <mode: 0 rayon, 2 single-thread>
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let d: u32 = args.get(1).and_then(|s| s.parse().ok()).unwrap_or(24);
    let reps: u32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(3);
    let mode: u32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(0);
    let words = 1usize << d;
    let mut buf = Vec::with_capacity(words * 4);
    for j in 0..words as u32 {
        buf.extend_from_slice(&(j.wrapping_mul(2654435761).wrapping_add(12345)).to_le_bytes());
    }
    for _ in 0..reps {
        let t = Instant::now();
        let h = if mode == 0 {
            blake3::Hasher::new().update_rayon(&buf).finalize()
        } else {
            blake3::hash(&buf)
        };
        let us = t.elapsed().as_micros();
        println!("us {} bytes {} {}", us, buf.len(), h.to_hex());
    }
}
