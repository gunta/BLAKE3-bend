// iroh-blobs ingest benchmark: how long iroh-blobs takes to add files to a
// store, which hashes them with BLAKE3 and builds their bao outboards (the
// tree of chaining values above 16 KiB chunk groups that verified streaming
// needs). Every round adds all files at once into a fresh store; prints
// "us <round microseconds> fold <xor of all hash words>", the same fold
// bench/daemon.bend prints, so the hashes are checked against Bend's.
//
// usage: iroh-ingest <fs|mem> <copy|ref> <rounds> FILE...
use futures::future::join_all;
use iroh_blobs::{
    api::{blobs::AddPathOptions, proto::ImportMode},
    store::{fs::FsStore, mem::MemStore},
    BlobFormat,
};
use std::{path::PathBuf, time::Instant};

fn fold(h: &iroh_blobs::Hash) -> u32 {
    h.as_bytes()
        .chunks(4)
        .fold(0u32, |x, w| x ^ u32::from_le_bytes([w[0], w[1], w[2], w[3]]))
}

#[tokio::main(flavor = "multi_thread")]
async fn main() -> anyhow_free::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let fs = args[1] == "fs";
    let mode = if args[2] == "ref" { ImportMode::TryReference } else { ImportMode::Copy };
    let rounds: usize = args[3].parse().unwrap();
    let paths: Vec<PathBuf> = args[4..]
        .iter()
        .map(|p| std::path::absolute(p).unwrap())
        .collect();
    for _ in 0..rounds {
        let dir = tempfile::tempdir_in(std::env::var("IROH_BENCH_DIR").unwrap_or(".".into()))
            .map_err(|e| e.to_string())?;
        let fs_store;
        let mem_store;
        let blobs = if fs {
            fs_store = FsStore::load(dir.path().join("store")).await.map_err(|e| e.to_string())?;
            fs_store.blobs().clone()
        } else {
            mem_store = MemStore::new();
            mem_store.blobs().clone()
        };
        let t = Instant::now();
        let tags = join_all(paths.iter().map(|p| {
            let blobs = blobs.clone();
            let p = p.clone();
            async move {
                blobs
                    .add_path_with_opts(AddPathOptions { path: p, format: BlobFormat::Raw, mode })
                    .await
            }
        }))
        .await;
        let us = t.elapsed().as_micros();
        let mut x = 0u32;
        for tag in tags {
            x ^= fold(&tag.map_err(|e| e.to_string())?.hash);
        }
        println!("us {us} fold {x}");
    }
    Ok(())
}

mod anyhow_free {
    pub type Result<T> = std::result::Result<T, String>;
}
