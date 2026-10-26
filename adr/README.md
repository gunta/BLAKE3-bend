# Architecture decision records

How the Bend2 BLAKE3 got fast, and what we measured on the way.

| ADR | decision |
|-----|----------|
| [0001](0001-bend2-blake3-baseline.md) | BLAKE3 core in Bend2, the baseline we race |
| [0002](0002-eight-lane-compress-and-slp.md) | 8-lane compress8 shaped for clang's SLP vectorizer; inline threshold |
| [0003](0003-b3sum-io-path.md) | b3sum I/O: parallel one-pass loader, zero-copy mmap, one-write output |
| [0004](0004-big-files-and-the-gpu.md) | files past 4 GiB as 1 GiB segments; the CLI stays on the CPU |
| [0005](0005-gpu-flat-leaves.md) | flat GPU leaves sized to the 16384-lane cube |
| [0006](0006-native-gpu-references.md) | native Metal and CUDA references; where Bend's GPU time goes (read-bound) |
| [0007](0007-laws-and-proofs.md) | LAWS.bend / PROOF.bend: known answers, lane laws, tree theorems; Array.fork moved to hash.bend |
| [0008](0008-daemon-map-zone-and-iroh-outboards.md) | daemon race, a zone for mapped files, iroh-blobs outboards, a progressive load |
| [0009](0009-streaming-uncached-files-and-gpu-daemon.md) | files not in the page cache streamed at SSD speed; a GPU daemon |
| [0010](0010-more-laws-outboards-counts-streaming.md) | more laws: the outboard tree's hash for every input, leaf and parent counts, the streaming stack |
| [0011](0011-strided-gpu-lanes-and-cpu-gpu-split.md) | strided GPU lanes past 512 MiB (1 GiB 13.2 -> 9.4 ms); the CPU and the GPU on one input, split by slices (8.0 ms, 1.06-1.12x the GPU alone) |
