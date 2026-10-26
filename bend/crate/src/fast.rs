//! turboblake's fast path.
//!
//! This is the official b3sum, on this crate's library, with three additions:
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
//! - --check reads its lines a batch at a time and hashes their files as a
//!   batch of arguments is hashed (`check_batch`).
//!
//! The engine is not faster on everything (ADR 0016). Starting it costs
//! about what a few small files cost upstream, and one big file in the page
//! cache is bound by its page faults, which upstream's mapping takes as fast
//! as the engine's. So a batch goes to the engine when it holds many files,
//! more than one big one, or a big one mostly on disk.

use super::{Args, FilepathString, filepath_to_string};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::fs::File;
use std::io::{self, BufRead, Read, Write};
#[cfg(unix)]
use std::os::unix::fs::FileExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
#[cfg(unix)]
use std::sync::mpsc;

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

#[cfg(unix)]
#[cfg(unix)]
/// Blocks of a read input: a power of two, so each is a whole subtree at
/// its offset, and `update_rayon` spreads it over every core.
const BLOCK: usize = 32 << 20;
/// Threads reading one block of a regular file at once (`read_at`): one
/// pread copies ~20 GB/s out of the page cache, about half what the cores
/// hash.
const READERS: usize = 4;

#[cfg(unix)]
/// Where read input comes from: a regular file (positional reads from an
/// offset, several at once) or anything else (in order).
pub(crate) enum Source<'a> {
    At(&'a File, u64),
    Seq(&'a mut (dyn Read + Send)),
}

#[cfg(unix)]
/// Upstream's `update_reader`, which reads 64 KiB at a time and hashes them
/// on one thread (~2 GB/s here): this reads `BLOCK`s on a thread of its
/// own while the block before hashes on every core. A regular file's block
/// takes `READERS` positional reads at once; either way it reads up to the
/// end, as upstream does, and maps nothing (--no-mmap, stdin).
pub(crate) fn update_read(hasher: &mut blake3::Hasher, mut src: Source) -> io::Result<u64> {
    let mut first = vec![0u8; BLOCK];
    let n = fill(&mut src, &mut first)?;
    if n < BLOCK {
        if (n as u64) < SERIAL_COLD {
            hasher.update(&first[..n]);
        } else {
            RAYON.store(true, Ordering::Relaxed);
            hasher.update_rayon(&first[..n]);
        }
        return Ok(n as u64);
    }
    RAYON.store(true, Ordering::Relaxed);
    let (full_tx, full_rx) = mpsc::sync_channel::<(Vec<u8>, usize)>(1);
    let (free_tx, free_rx) = mpsc::sync_channel::<Vec<u8>>(2);
    free_tx.send(vec![0u8; BLOCK]).ok();
    std::thread::scope(|s| {
        let reader = s.spawn(move || -> io::Result<()> {
            while let Ok(mut buf) = free_rx.recv() {
                let n = fill(&mut src, &mut buf)?;
                if n == 0 || full_tx.send((buf, n)).is_err() || n < BLOCK {
                    break;
                }
            }
            Ok(())
        });
        let mut total = n as u64;
        hasher.update_rayon(&first);
        free_tx.send(first).ok();
        // every block the reader sent, to the last: it may be done reading
        // (and the buffer not wanted back) before this one hashes
        for (buf, n) in full_rx {
            hasher.update_rayon(&buf[..n]);
            total += n as u64;
            free_tx.send(buf).ok();
        }
        drop(free_tx);
        reader.join().expect("turboblake: reader panicked")?;
        Ok(total)
    })
}

#[cfg(unix)]
/// Fills buf up to its end or the input's, and says how far.
fn fill(src: &mut Source, buf: &mut [u8]) -> io::Result<usize> {
    match src {
        Source::Seq(r) => read_full(|b, _| r.read(b), buf),
        Source::At(f, off) => {
            let (file, at): (&File, u64) = (f, *off);
            let per = buf.len().div_ceil(READERS);
            let got: Vec<io::Result<usize>> = std::thread::scope(|s| {
                let parts: Vec<_> = buf
                    .chunks_mut(per)
                    .enumerate()
                    .map(|(i, part)| s.spawn(move || read_full(|b, k| file.read_at(b, at + (i * per + k) as u64), part)))
                    .collect();
                parts.into_iter().map(|h| h.join().expect("turboblake: reader panicked")).collect()
            });
            // the input ends where the first part came up short
            let mut n = 0;
            for (i, g) in got.into_iter().enumerate() {
                let g = g?;
                n += g;
                if g < per.min(buf.len() - i * per) {
                    break;
                }
            }
            *off += n as u64;
            Ok(n)
        }
    }
}

#[cfg(unix)]
/// Reads into buf until it is full or the input ends; retries interrupts.
/// read gets the rest of buf and how much of it is already read.
fn read_full(mut read: impl FnMut(&mut [u8], usize) -> io::Result<usize>, buf: &mut [u8]) -> io::Result<usize> {
    let mut n = 0;
    while n < buf.len() {
        match read(&mut buf[n..], n) {
            Ok(0) => break,
            Ok(k) => n += k,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
    Ok(n)
}

/// A file opened for --no-mmap: read as `update_read` reads, from its start.
#[cfg(not(unix))]
pub(crate) fn update_file(hasher: &mut blake3::Hasher, file: File) -> io::Result<()> {
    hasher.update_reader(file).map(|_| ())
}

/// A file opened for --no-mmap: read as `update_read` reads, from its start.
#[cfg(unix)]
pub(crate) fn update_file(hasher: &mut blake3::Hasher, file: File) -> io::Result<()> {
    if file.metadata()?.is_file() {
        update_read(hasher, Source::At(&file, 0))?;
    } else {
        let mut file = file;
        update_read(hasher, Source::Seq(&mut file))?;
    }
    Ok(())
}

/// Standard input, read as `update_read` reads: from where its offset is
/// to the end, and the offset left at the end, as reading it leaves it.
/// Read through fd 0 itself: nothing has read stdin's buffer before this.
#[cfg(not(unix))]
pub(crate) fn update_stdin(hasher: &mut blake3::Hasher) -> io::Result<()> {
    hasher.update_reader(io::stdin().lock()).map(|_| ())
}

/// Standard input, read as `update_read` reads: from where its offset is
/// to the end, and the offset left at the end, as reading it leaves it.
/// Read through fd 0 itself: nothing has read stdin's buffer before this.
#[cfg(unix)]
pub(crate) fn update_stdin(hasher: &mut blake3::Hasher) -> io::Result<()> {
    use std::io::Seek;
    use std::os::fd::FromRawFd;
    let _lock = io::stdin().lock();
    // SAFETY: fd 0 stays open for the process; ManuallyDrop never closes it.
    let file = std::mem::ManuallyDrop::new(unsafe { File::from_raw_fd(0) });
    let mut f: &File = &file;
    match (file.metadata(), f.stream_position()) {
        (Ok(m), Ok(at)) if m.is_file() => {
            let n = update_read(hasher, Source::At(&file, at))?;
            f.seek(io::SeekFrom::Start(at + n))?;
        }
        _ => {
            update_read(hasher, Source::Seq(&mut f))?;
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
            && std::env::var("TURBOBLAKE").as_deref() != Ok("0");
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

// --check: a batch of lines at a time, their files hashed as `Batch` hashes
// a batch of arguments; check_one_line takes each file's hash in order.
thread_local! {
    static CHECKED: RefCell<VecDeque<(PathBuf, io::Result<blake3::Hash>)>> = const { RefCell::new(VecDeque::new()) };
}

/// Reads the next `BATCH` lines of a checkfile, and has the engine hash
/// their files at once if it is faster on them (see `Batch`).
pub(crate) fn check_batch(lines: &mut dyn BufRead, args: &Args) -> io::Result<Vec<String>> {
    let mut batch = Vec::new();
    while batch.len() < BATCH {
        let mut line = String::new();
        if lines.read_line(&mut line)? == 0 {
            break;
        }
        batch.push(line);
    }
    let on = !args.no_mmap() && std::env::var("TURBOBLAKE").as_deref() != Ok("0");
    let files: Vec<PathBuf> = batch
        .iter()
        .filter_map(|l| super::parse_check_line(l).ok().map(|p| p.file_path))
        .filter(|p| p.as_path() != Path::new("-"))
        .collect();
    let paths: Vec<&Path> = files.iter().map(|p| p.as_path()).collect();
    CHECKED.with_borrow_mut(|c| c.clear());
    if on && engine_wins(&paths) {
        if let Some(rs) = blake3::bend::hash_files(&paths) {
            CHECKED.with_borrow_mut(|c| c.extend(files.iter().cloned().zip(rs)));
        }
    }
    Ok(batch)
}

/// The hash the engine found for the next checked file, if it took it.
pub(crate) fn checked(path: &Path) -> Option<anyhow::Result<blake3::Hash>> {
    CHECKED.with_borrow_mut(|c| {
        if c.front().is_none_or(|(p, _)| p != path) {
            c.clear();
            return None;
        }
        match c.pop_front()?.1 {
            Err(e) if e.kind() == io::ErrorKind::Unsupported => None,
            r => Some(r.map_err(Into::into)),
        }
    })
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
