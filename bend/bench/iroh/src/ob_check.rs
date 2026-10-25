// Checks Bend's bao outboards (bench/obao.bend) against bao-tree, the
// library iroh-blobs builds its outboards with: for each file, the
// pre-order outboard over 16 KiB chunk groups (iroh's IROH_BLOCK_SIZE),
// byte for byte, and the root hash.
//
// usage: ob-check DIR FILE...   (DIR holds <name>.obao from bench/obao)
use bao_tree::{io::outboard::PreOrderMemOutboard, BlockSize};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let dir = std::path::Path::new(&args[1]);
    let mut bad = 0;
    for path in &args[2..] {
        let file = std::fs::File::open(path).expect("open");
        let map = unsafe { memmap2::Mmap::map(&file).expect("mmap") };
        let want = PreOrderMemOutboard::create(&map[..], BlockSize::from_chunk_log(4));
        let name = std::path::Path::new(path).file_name().unwrap().to_string_lossy();
        let got = std::fs::read(dir.join(format!("{name}.obao"))).unwrap_or_default();
        let ok = got == want.data;
        if !ok {
            bad += 1;
        }
        println!(
            "{} {} {} bytes of outboard, root {}",
            if ok { "ok " } else { "BAD" },
            name,
            want.data.len(),
            want.root.to_hex()
        );
    }
    if bad > 0 {
        eprintln!("{bad} outboards differ");
        std::process::exit(1);
    }
}
