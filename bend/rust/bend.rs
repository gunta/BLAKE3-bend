//! The Bend engine, for big subtrees.
//!
//! This crate is the official `blake3` crate with one hook:
//! `compress_subtree_to_parent_node`, the work `Hasher::update` (and
//! `hash`, and `update_rayon`) does for a subtree of two chunks or more,
//! asks this module first. A subtree big enough to beat the trip goes to the
//! Bend engine (bend/lib/engine.bend, compiled from `csrc/engine.c`), which
//! runs on a thread of its own for the life of the process and hashes it on
//! every core. Everything else is upstream's code.
//!
//! The engine's work: spans of at most 1 GiB (whole subtrees but the last),
//! each answered with its chaining value. Here they merge, as parent nodes,
//! into the two child CVs upstream expects, exactly as `blake3_bend.c` does
//! for the C library.
//!
//! [`hash_files`] is the engine's other job, turboblake's fast path.
//!
//! Environment: `BLAKE3_BEND=0` turns it off, `BLAKE3_BEND_MIN=<bytes>` sets
//! the smallest subtree it takes (otherwise calibrated at the first big
//! one), `BLAKE3_BEND_THREADS=<n>` caps its threads, `BLAKE3_BEND_TRACE=1`
//! prints what it did.

use crate::Hash;
use std::io;
use std::path::Path;

/// Hashes many files at once, as `turboblake` does: opened, mapped or read
/// in parallel, files not in the page cache streamed at SSD speed, every
/// file's tree hashed by the Bend engine at the same time. Each answer is
/// the file's `blake3::hash`, or the error opening or reading it. `None`
/// when this build has no engine (no clang, or not Unix): hash them one by
/// one then. A pipe or device comes back as an `Unsupported` error ("not a
/// regular file"), unread: read it with `Hasher::update_reader`.
pub fn hash_files(paths: &[&Path]) -> Option<Vec<io::Result<Hash>>> {
    #[cfg(all(blake3_bend, unix))]
    {
        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;
        let c: Vec<CString> = paths
            .iter()
            .map(|p| CString::new(p.as_os_str().as_bytes()).ok())
            .collect::<Option<_>>()?;
        let ptrs: Vec<*const core::ffi::c_char> = c.iter().map(|s| s.as_ptr()).collect();
        let mut out = vec![[0u8; 32]; paths.len()];
        let mut err = vec![0i32; paths.len()];
        let ok = unsafe { engine::b3e_files(paths.len() as u32, ptrs.as_ptr(), out.as_mut_ptr(), err.as_mut_ptr()) };
        if ok != 1 {
            return None;
        }
        Some(
            out.into_iter()
                .zip(err)
                .map(|(h, e)| match e {
                    0 => Ok(Hash::from_bytes(h)),
                    -1 => Err(io::Error::new(io::ErrorKind::Unsupported, "not a regular file")),
                    e => Err(io::Error::from_raw_os_error(e)),
                })
                .collect(),
        )
    }
    #[cfg(not(all(blake3_bend, unix)))]
    {
        let _ = paths;
        None
    }
}

#[cfg(blake3_bend)]
pub(crate) use engine::subtree;

#[cfg(blake3_bend)]
mod engine {
use crate::platform::Platform;
use crate::{BLOCK_LEN, CHUNK_LEN, CVWords, IV, OUT_LEN, PARENT};
use core::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Once;
use std::time::Instant;

unsafe extern "C" {
    fn b3e_hash(n: u32, p: *const *const u8, len: *const u64, cb: *const u64, out: *mut [u8; 32]) -> i32;
    fn b3e_hash_k(
        n: u32,
        p: *const *const u8,
        len: *const u64,
        cb: *const u64,
        key: *const u32,
        kf: u32,
        out: *mut [u8; 32],
    ) -> i32;
    fn b3e_inside(p: *const u8, len: u64) -> i32;
    pub(super) fn b3e_files(n: u32, paths: *const *const core::ffi::c_char, out: *mut [u8; 32], err: *mut i32) -> i32;
}

const SPAN_MAX: usize = 1 << 30;
const SPAN_COPY: usize = 64 << 20;
const PROBE: usize = 256 * 1024;
const UNSET: usize = usize::MAX - 1;

static MIN: AtomicUsize = AtomicUsize::new(UNSET);
static CALIBRATE: Once = Once::new();

fn fixed_min() -> Option<usize> {
    if std::env::var("BLAKE3_BEND").as_deref() == Ok("0") {
        return Some(usize::MAX);
    }
    std::env::var("BLAKE3_BEND_MIN")
        .ok()
        .and_then(|m| m.parse::<usize>().ok())
        .filter(|&m| m >= 2 * CHUNK_LEN)
}

// The engine costs a fixed O per job (waking its threads), then runs ~10x
// the one-thread SIMD rate R; it takes subtrees from 2 * O * R bytes.
fn calibrate(input: &[u8], platform: Platform) -> usize {
    let mut o = f64::MAX;
    let mut cv = [[0u8; 32]; 1];
    let p = [input.as_ptr()];
    let len = [2 * CHUNK_LEN as u64];
    let cb = [0u64];
    for _ in 0..4 {
        let t = Instant::now();
        if unsafe { b3e_hash(1, p.as_ptr(), len.as_ptr(), cb.as_ptr(), cv.as_mut_ptr()) } != 1 {
            return usize::MAX;
        }
        o = o.min(t.elapsed().as_secs_f64());
    }
    let mut r = f64::MAX;
    let mut cvs = [0u8; crate::platform::MAX_SIMD_DEGREE_OR_2 * OUT_LEN];
    for _ in 0..2 {
        let t = Instant::now();
        crate::compress_subtree_wide::<crate::join::SerialJoin>(
            &input[..PROBE],
            IV,
            0,
            0,
            platform,
            &mut cvs,
        );
        r = r.min(t.elapsed().as_secs_f64());
    }
    let min = (2.0 * o * (PROBE as f64 / r)).clamp(64.0 * 1024.0, 64.0 * 1024.0 * 1024.0) as usize;
    if std::env::var_os("BLAKE3_BEND_TRACE").is_some() {
        eprintln!(
            "blake3-bend: engine {:.1} us a job, Rust {:.2} GB/s: subtrees from {} bytes",
            o * 1e6,
            PROBE as f64 / r / 1e9,
            min
        );
    }
    min
}

fn min_len(input: &[u8], platform: Platform) -> usize {
    let m = MIN.load(Ordering::Relaxed);
    if m != UNSET {
        return m;
    }
    if let Some(f) = fixed_min() {
        MIN.store(f, Ordering::Relaxed);
        return f;
    }
    if input.len() < PROBE {
        return usize::MAX;
    }
    CALIBRATE.call_once(|| MIN.store(calibrate(input, platform), Ordering::Relaxed));
    MIN.load(Ordering::Relaxed)
}

fn parent(key: &CVWords, flags: u8, l: &[u8; 32], r: &[u8; 32], platform: Platform) -> [u8; 32] {
    let mut block = [0u8; BLOCK_LEN];
    block[..32].copy_from_slice(l);
    block[32..].copy_from_slice(r);
    let mut cv = *key;
    platform.compress_in_place(&mut cv, &block, BLOCK_LEN as u8, 0, flags | PARENT);
    crate::platform::le_bytes_from_words_32(&cv)
}

// Merges span CVs as BLAKE3's left-full tree.
fn merge(key: &CVWords, flags: u8, cvs: &[[u8; 32]], platform: Platform) -> [u8; 32] {
    if cvs.len() == 1 {
        return cvs[0];
    }
    let mut p = 1;
    while p * 2 <= cvs.len() - 1 {
        p *= 2;
    }
    let l = merge(key, flags, &cvs[..p], platform);
    let r = merge(key, flags, &cvs[p..], platform);
    parent(key, flags, &l, &r, platform)
}

/// The two child CVs of `input` (2+ chunks, any length) as a subtree from
/// `chunk_counter`, hashed by the engine; `None` when upstream's code should
/// hash it (too small to beat the trip, or no engine).
pub(crate) fn subtree(
    input: &[u8],
    key: &CVWords,
    chunk_counter: u64,
    flags: u8,
    platform: Platform,
) -> Option<[u8; BLOCK_LEN]> {
    if input.len() <= CHUNK_LEN || input.len() < min_len(input, platform) {
        return None;
    }
    // Spans the engine reads in place are up to 1 GiB; copied ones 64 MiB,
    // so their copies overlap the hashing of the ones before.
    let left = crate::hazmat::left_subtree_len(input.len() as u64) as usize;
    let whole = input.len() - input.len() % 64;
    let most = if unsafe { b3e_inside(input.as_ptr(), whole as u64) } != 0 { SPAN_MAX } else { SPAN_COPY };
    let span = left.min(most);
    let nl = left / span;
    let n = nl + (input.len() - left).div_ceil(span);
    // Every mode (key and flags), and 64-bit chunk counters: each span keeps
    // its counter's high word, since a subtree's counter is a multiple of its
    // size, so spans (powers of two of at most 2^20 chunks) start at multiples
    // of theirs and none crosses a multiple of 2^32.
    if chunk_counter % (span / CHUNK_LEN) as u64 != 0 {
        return None;
    }
    let mut p = Vec::with_capacity(n);
    let mut len = Vec::with_capacity(n);
    let mut cb = Vec::with_capacity(n);
    for i in 0..n {
        let at = i * span;
        p.push(input[at..].as_ptr());
        len.push((input.len() - at).min(span) as u64);
        cb.push(chunk_counter + (at / CHUNK_LEN) as u64);
    }
    let mut cvs = vec![[0u8; 32]; n];
    let ok = unsafe {
        b3e_hash_k(n as u32, p.as_ptr(), len.as_ptr(), cb.as_ptr(), key.as_ptr(), flags as u32, cvs.as_mut_ptr())
    };
    if ok != 1 {
        return None;
    }
    let mut out = [0u8; BLOCK_LEN];
    out[..32].copy_from_slice(&merge(key, flags, &cvs[..nl], platform));
    out[32..].copy_from_slice(&merge(key, flags, &cvs[nl..], platform));
    Some(out)
}
}
