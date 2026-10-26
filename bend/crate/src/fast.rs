//! turboblake's fast path.
//!
//! This is the official b3sum, built on blake3-bend, with one addition: in
//! the default mode (32-byte output, no seek, no --keyed, --derive-key,
//! --check or --no-mmap), the files are hashed many at a time by the Bend
//! engine (`blake3::bend::hash_files`): opened in parallel, mapped or read,
//! files not in the page cache streamed at SSD speed, every file's tree at
//! once. Each file's line is then printed by the same code as upstream's, in
//! order. Anything the engine does not take (stdin, pipes, devices, a build
//! with no engine) goes through upstream's `hash_one_input`.

use super::{Args, FilepathString, filepath_to_string};
use std::io::{self, Write};
use std::path::Path;

/// Files a batch: bounds the memory of files read into the heap, and keeps
/// lines coming for a long list.
const BATCH: usize = 2048;

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
