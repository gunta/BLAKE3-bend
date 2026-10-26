//! The official crate's answers for the tests past 4 TiB.
//!
//! usage: hiref NAME LEN COUNTER [NAME LEN COUNTER]...
//!   test/hi.bend's spans: each a subtree at an input offset (hazmat), in the
//!   default and the keyed mode, one line a case.
//! usage: hiref --file PATH
//!   a sparse file's hash, "<hash>  PATH" as b3sum prints it, reading only
//!   its data (SEEK_DATA): each 1 GiB segment is a subtree at its offset,
//!   zeros but for the data in it, and the segments merge as BLAKE3's tree.
use official::hazmat::{merge_subtrees_non_root, merge_subtrees_root, ChainingValue, HasherExt, Mode};
use official::{Hasher, CHUNK_LEN};
use std::os::unix::fs::FileExt;
use std::os::unix::io::AsRawFd;

const SEG: u64 = 1 << 30;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn spans(args: &[String]) {
    let key: [u8; 32] = core::array::from_fn(|i| i as u8);
    for case in args.chunks(3) {
        let (name, len, ctr) = (&case[0], case[1].parse::<usize>().unwrap(), case[2].parse::<u64>().unwrap());
        let input: Vec<u8> = (0..len).map(|i| (i % 251) as u8).collect();
        let at = ctr * CHUNK_LEN as u64;
        let cv = hex(&Hasher::new().set_input_offset(at).update_rayon(&input).finalize_non_root());
        let kcv = hex(&Hasher::new_keyed(&key).set_input_offset(at).update_rayon(&input).finalize_non_root());
        println!("{name} cpu {cv} gpu {cv} ob {cv} keyed {kcv} tree1 {cv}");
    }
}

unsafe extern "C" {
    fn lseek(fd: i32, off: i64, whence: i32) -> i64;
}

#[cfg(target_os = "macos")]
const SEEK_HOLE: i32 = 3;
#[cfg(target_os = "macos")]
const SEEK_DATA: i32 = 4;
#[cfg(not(target_os = "macos"))]
const SEEK_DATA: i32 = 3;
#[cfg(not(target_os = "macos"))]
const SEEK_HOLE: i32 = 4;

// The CVs of segments lo..hi as BLAKE3's left-full tree: the left side
// takes the largest power of two of segments below the count.
fn merge(cvs: &[ChainingValue]) -> ChainingValue {
    if cvs.len() == 1 {
        return cvs[0];
    }
    let mut left = 1;
    while left * 2 < cvs.len() {
        left *= 2;
    }
    merge_subtrees_non_root(&merge(&cvs[..left]), &merge(&cvs[left..]), Mode::Hash)
}

fn file(path: &str) {
    let f = std::fs::File::open(path).unwrap();
    let len = f.metadata().unwrap().len();
    assert!(len > SEG, "a file of more than one segment");
    let fd = f.as_raw_fd();
    let nseg = len.div_ceil(SEG);
    let zeros = vec![0u8; SEG as usize];
    let mut buf = vec![0u8; SEG as usize];
    let (mut cvs, mut extents, mut bytes) = (Vec::new(), 0, 0);
    for k in 0..nseg {
        let (off, n) = (k * SEG, (len - k * SEG).min(SEG));
        let mut seg: &[u8] = &zeros[..n as usize];
        let mut at = off;
        while at < off + n {
            let d = unsafe { lseek(fd, at as i64, SEEK_DATA) };
            if d < 0 || d as u64 >= off + n {
                break;
            }
            let h = (unsafe { lseek(fd, d, SEEK_HOLE) } as u64).min(off + n);
            if seg.as_ptr() == zeros.as_ptr() {
                buf[..n as usize].fill(0);
            }
            let (d, h) = (d as u64, h);
            f.read_exact_at(&mut buf[(d - off) as usize..(h - off) as usize], d).unwrap();
            seg = &buf[..n as usize];
            extents += 1;
            bytes += h - d;
            at = h;
        }
        cvs.push(Hasher::new().set_input_offset(off).update_rayon(seg).finalize_non_root());
    }
    let mut left = 1;
    while left * 2 < cvs.len() {
        left *= 2;
    }
    let root = merge_subtrees_root(&merge(&cvs[..left]), &merge(&cvs[left..]), Mode::Hash);
    eprintln!("hiref: {nseg} segments, {extents} data extents ({bytes} bytes read)");
    println!("{}  {path}", root.to_hex());
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("--file") => file(&args[1]),
        _ => spans(&args),
    }
}
