//! turboblake's fast path.
//!
//! This is the official b3sum, built on blake3-bend, with three additions:
//!
//! - In the default mode (32-byte output, no seek, no --keyed, --derive-key,
//!   --check or --no-mmap), a batch of files the engine is faster on is
//!   hashed many at a time by the Bend engine (`blake3::bend::hash_files`):
//!   opened in parallel, mapped or read, files not in the page cache
//!   streamed at SSD speed, every file's tree at once. Each file's line is
//!   then printed by the same code as upstream's, in order.
//! - Everything else goes through upstream's `hash_one_input`, where a small
//!   file is hashed on one thread (`update_path`): starting rayon's threads
//!   costs more than they save on it.
//! - rayon's threads start when a file first needs them (`pool`), not
//!   before the first file.
//!
//! The engine is not faster on everything (ADR 0013). Starting it costs
//! about what a few small files cost upstream, and one big file in the page
//! cache is bound by its page faults, which upstream's mapping takes as fast
//! as the engine's. So a batch goes to the engine when it holds many files,
//! more than one big one, or a big one mostly on disk.

use super::{Args, FilepathString, filepath_to_string};
use std::io::{self, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};

/// Files a batch: bounds the memory of files read into the heap, and keeps
/// lines coming for a long list.
const BATCH: usize = 2048;
/// A batch of more files than this goes to the engine unseen (its parallel
/// opens win); a smaller one is looked at first.
const FEW: usize = 16;
/// The engine overlaps big files' page faults, one file's with another's:
/// it takes a few files when, past the biggest, they hold this much.
const REST: u64 = 32 << 20;
/// A file from this size, mostly on disk, is streamed by the engine.
const STREAM: u64 = 256 << 20;
/// Below this size a file is hashed on one thread while rayon's threads
/// have not started (starting 18 costs ~0.3 ms, what they save on 1 MiB),
/// and below `SERIAL_WARM` once they have.
const SERIAL_COLD: u64 = 1 << 20;
const SERIAL_WARM: u64 = 128 << 10;

/// rayon's threads are running.
static RAYON: AtomicBool = AtomicBool::new(false);

/// Runs main's work in a pool of n threads if --num-threads asked for one,
/// as upstream does; otherwise in rayon's global pool, whose threads start
/// when a file first needs them.
pub(crate) fn pool<R: Send>(n: Option<usize>, work: impl FnOnce() -> R + Send) -> anyhow::Result<R> {
    match n {
        Some(n) => {
            RAYON.store(true, Ordering::Relaxed);
            Ok(rayon_core::ThreadPoolBuilder::new().num_threads(n).build()?.install(work))
        }
        None => Ok(work()),
    }
}

/// Upstream's `update_mmap_rayon`, on one thread for a small file.
pub(crate) fn update_path(hasher: &mut blake3::Hasher, path: &Path) -> io::Result<()> {
    let serial = if RAYON.load(Ordering::Relaxed) { SERIAL_WARM } else { SERIAL_COLD };
    match std::fs::metadata(path) {
        Ok(m) if m.is_file() && m.len() < serial => {
            hasher.update_mmap(path)?;
        }
        _ => {
            RAYON.store(true, Ordering::Relaxed);
            hasher.update_mmap_rayon(path)?;
        }
    }
    Ok(())
}

pub(crate) struct Batch<'a> {
    args: &'a Args,
    on: bool,
    lo: usize,
    hashes: Vec<Option<io::Result<blake3::Hash>>>,
}

impl<'a> Batch<'a> {
    pub(crate) fn new(args: &'a Args) -> Self {
        let on = !args.check()
            && !args.keyed()
            && args.inner.derive_key.is_none()
            && args.len() == blake3::OUT_LEN as u64
            && args.seek() == 0
            && !args.no_mmap()
            && std::env::var("BLAKE3_BEND").as_deref() != Ok("0");
        Batch { args, on, lo: 0, hashes: Vec::new() }
    }

    /// File i's hash, if the engine took it. Call with i in order.
    pub(crate) fn take(&mut self, i: usize) -> Option<io::Result<blake3::Hash>> {
        if !self.on {
            return None;
        }
        if i < self.lo || i >= self.lo + self.hashes.len() {
            self.load(i);
        }
        match self.hashes.get_mut(i - self.lo)?.take()? {
            Err(e) if e.kind() == io::ErrorKind::Unsupported => None,
            r => Some(r),
        }
    }

    fn load(&mut self, lo: usize) {
        let all = &self.args.file_args;
        let hi = (lo + BATCH).min(all.len());
        let mut which = Vec::new();
        let mut paths: Vec<&Path> = Vec::new();
        for (i, p) in all[lo..hi].iter().enumerate() {
            if p.as_path() != Path::new("-") {
                which.push(i);
                paths.push(p);
            }
        }
        self.lo = lo;
        self.hashes = (lo..hi).map(|_| None).collect();
        if !engine_wins(&paths) {
            return;
        }
        match blake3::bend::hash_files(&paths) {
            Some(rs) => {
                for (i, r) in which.into_iter().zip(rs) {
                    self.hashes[i] = Some(r);
                }
            }
            None => self.on = false,
        }
    }
}

/// Whether the engine hashes these files faster than upstream, one by one.
fn engine_wins(paths: &[&Path]) -> bool {
    if paths.len() > FEW {
        return true;
    }
    let mut sizes: Vec<(u64, &Path)> = paths
        .iter()
        .filter_map(|p| std::fs::metadata(p).ok().filter(|m| m.is_file()).map(|m| (m.len(), *p)))
        .collect();
    sizes.sort_by(|a, b| b.0.cmp(&a.0));
    let Some(&(top, biggest)) = sizes.first() else {
        return false;
    };
    let rest: u64 = sizes[1..].iter().map(|s| s.0).sum();
    rest >= REST || (top >= STREAM && blake3::bend::cached(biggest) == Some(false))
}

/// Prints one file's line from its hash, as `hash_one_input` does.
pub(crate) fn print(path: &Path, hash: io::Result<blake3::Hash>, args: &Args) -> anyhow::Result<()> {
    let hash = hash?;
    if args.raw() {
        io::stdout().lock().write_all(hash.as_bytes())?;
        return Ok(());
    }
    if args.no_names() {
        println!("{}", hash.to_hex());
        return Ok(());
    }
    let FilepathString {
        filepath_string,
        is_escaped,
    } = filepath_to_string(path);
    if is_escaped {
        print!("\\");
    }
    if args.tag() {
        println!("BLAKE3 ({}) = {}", filepath_string, hash.to_hex());
        return Ok(());
    }
    println!("{}  {}", hash.to_hex(), filepath_string);
    Ok(())
}
