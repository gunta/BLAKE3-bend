//! The official blake3 crate against blake3-bend, in memory: `hash` (one
//! thread upstream) and `Hasher::update_rayon` (every core upstream), on
//! the same buffer, interleaved; prints medians and checks the digests.
//!   cargo run --release [reps]
use std::time::Instant;

fn median(mut v: Vec<f64>) -> f64 {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    v[v.len() / 2]
}

fn main() {
    let reps: usize = std::env::args().nth(1).and_then(|s| s.parse().ok()).unwrap_or(9);
    let sizes = [1 << 10, 64 << 10, 1 << 20, 16 << 20, 64 << 20, 256 << 20, 1 << 30];
    let buf: Vec<u8> = (0..1usize << 30).map(|i| (i.wrapping_mul(2654435761) >> 13) as u8).collect();
    println!("| bytes | blake3 hash | blake3 update_rayon | blake3-bend hash | blake3-bend update_rayon | digest |");
    println!("|---:|---:|---:|---:|---:|:---:|");
    for &n in &sizes {
        let input = &buf[..n];
        let r = if n >= 256 << 20 { reps.min(5) } else { reps };
        let mut t = [vec![], vec![], vec![], vec![]];
        let mut d = [String::new(), String::new(), String::new(), String::new()];
        for i in 0..=r {
            let s = Instant::now();
            let a = official::hash(input);
            let ta = s.elapsed().as_secs_f64();
            let s = Instant::now();
            let b = official::Hasher::new().update_rayon(input).finalize();
            let tb = s.elapsed().as_secs_f64();
            let s = Instant::now();
            let c = bend::hash(input);
            let tc = s.elapsed().as_secs_f64();
            let s = Instant::now();
            let e = bend::Hasher::new().update_rayon(input).finalize();
            let te = s.elapsed().as_secs_f64();
            if i > 0 {
                for (k, x) in [ta, tb, tc, te].into_iter().enumerate() {
                    t[k].push(x * 1e3);
                }
            }
            d = [a.to_hex().to_string(), b.to_hex().to_string(), c.to_hex().to_string(), e.to_hex().to_string()];
        }
        let same = d.iter().all(|x| *x == d[0]);
        let size = if n >= 1 << 30 { format!("{} GiB", n >> 30) } else if n >= 1 << 20 { format!("{} MiB", n >> 20) } else { format!("{} KiB", n >> 10) };
        let m: Vec<f64> = t.into_iter().map(median).collect();
        println!("| {size} | {:.3} ms | {:.3} ms | {:.3} ms | {:.3} ms | {} |", m[0], m[1], m[2], m[3], if same { "ok" } else { "DIFFER" });
    }
}
