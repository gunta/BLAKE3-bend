//! The GPU (ADR 0017).
//!
//! turboblake runs the hand-written Metal and CUDA BLAKE3 kernels where they
//! measure faster than the CPU. They are loaded at run time: Metal.framework
//! on macOS, `libcuda`'s driver API elsewhere, with the kernels shipped as
//! PTX. A machine without a GPU or a driver, a build without the backend
//! (no clang), or `TURBOBLAKE_GPU=0` keeps everything on the CPU: [`backend`]
//! is `None`, the updates below answer `false`, [`Memory::new`] is `None`.
//!
//! - GPU memory: [`Hasher::update_metal`] and [`Hasher::update_cuda`] feed a
//!   Metal buffer or a CUDA device pointer to any hasher, which the GPU
//!   hashes where the bytes are (model weights, checkpoints).
//! - Host memory the GPU reads in place ([`Memory`]: a shared Metal buffer on
//!   Apple silicon, pinned memory on NVIDIA): `Hasher::update` over it splits
//!   big subtrees between the CPU (the Bend engine) and the GPU, at the share
//!   their measured rates balance.
//!
//! The C side is `turboblake_gpu.c` (bend/lib), which the C library shares.
//! Environment: `TURBOBLAKE_GPU=0` turns it off; `TURBOBLAKE_GPU=all` makes
//! the GPU take every subtree (for tests); `TURBOBLAKE_GPU_MIN=<bytes>` the
//! smallest subtree it takes; `TURBOBLAKE_GPU_SHARE=<0..1>` its share of a
//! split.

use crate::Hasher;
use core::ffi::c_void;

/// The GPU backend this process runs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Backend {
    /// Metal, on macOS.
    Metal,
    /// CUDA, through libcuda's driver API.
    Cuda,
}

/// The backend, loading it on the first call: `None` without a GPU, a
/// driver, or a build with the backend.
pub fn backend() -> Option<Backend> {
    #[cfg(turboblake_gpu)]
    {
        match unsafe { ffi::tbg_backend() } {
            1 => return Some(Backend::Metal),
            2 => return Some(Backend::Cuda),
            _ => {}
        }
    }
    None
}

#[cfg(turboblake_gpu)]
pub(crate) mod ffi {
    use core::ffi::c_void;

    pub const METAL: i32 = 1;
    pub const CUDA: i32 = 2;

    unsafe extern "C" {
        pub fn tbg_backend() -> i32;
        pub fn tbg_subtree(input: *const u8, len: u64, key: *const u32, ctr: u64, flags: u8, out: *mut u8) -> i32;
        pub fn tbg_dev_subtree(
            kind: i32,
            obj: *mut c_void,
            off: u64,
            len: u64,
            stream: *mut c_void,
            key: *const u32,
            ctr: u64,
            flags: u8,
            out: *mut u8,
        ) -> i32;
        pub fn tbg_dev_min() -> u64;
        pub fn tbg_read(kind: i32, obj: *mut c_void, off: u64, len: u64, stream: *mut c_void, dst: *mut u8) -> i32;
        pub fn tbg_metal_contents(buffer: *mut c_void, len: *mut u64) -> *mut u8;
        pub fn tbg_alloc(len: usize) -> *mut u8;
        pub fn tbg_free(p: *mut u8);
        pub fn tbg_register_metal(buffer: *mut c_void) -> i32;
        pub fn tbg_unregister(p: *mut u8);
        #[cfg(test)]
        pub fn tbg_upload(p: *const u8, len: u64, pad: u64, gpu_only: i32) -> *mut c_void;
        #[cfg(test)]
        pub fn tbg_drop(obj: *mut c_void);
    }
}

/// The two child CVs of a subtree in host memory the GPU was given (or any,
/// under `TURBOBLAKE_GPU=all`), hashed on the GPU alone or beside the engine;
/// `None` when it is not the GPU's.
#[cfg(turboblake_gpu)]
pub(crate) fn subtree(input: &[u8], key: &crate::CVWords, chunk_counter: u64, flags: u8) -> Option<[u8; 64]> {
    let mut out = [0u8; 64];
    let ok = unsafe {
        ffi::tbg_subtree(input.as_ptr(), input.len() as u64, key.as_ptr(), chunk_counter, flags, out.as_mut_ptr())
    };
    (ok == 1).then_some(out)
}

/// Host memory the GPU reads in place: a shared Metal buffer on Apple
/// silicon, pinned memory on NVIDIA. `Hasher::update` over it splits big
/// subtrees between the CPU and the GPU. Zeroed on Metal; its contents are
/// unspecified on CUDA until written.
pub struct Memory {
    ptr: core::ptr::NonNull<u8>,
    len: usize,
}

// The memory is plain bytes; the backend keeps its own bookkeeping locked.
unsafe impl Send for Memory {}
unsafe impl Sync for Memory {}

impl Memory {
    /// `len` bytes, or `None` without a GPU backend (allocate a `Vec` then).
    pub fn new(len: usize) -> Option<Self> {
        #[cfg(turboblake_gpu)]
        {
            if len > 0 {
                let p = unsafe { ffi::tbg_alloc(len) };
                return core::ptr::NonNull::new(p).map(|ptr| Self { ptr, len });
            }
        }
        let _ = len;
        None
    }
}

impl core::ops::Deref for Memory {
    type Target = [u8];
    fn deref(&self) -> &[u8] {
        unsafe { core::slice::from_raw_parts(self.ptr.as_ptr(), self.len) }
    }
}

impl core::ops::DerefMut for Memory {
    fn deref_mut(&mut self) -> &mut [u8] {
        unsafe { core::slice::from_raw_parts_mut(self.ptr.as_ptr(), self.len) }
    }
}

impl Drop for Memory {
    fn drop(&mut self) {
        #[cfg(turboblake_gpu)]
        unsafe {
            ffi::tbg_free(self.ptr.as_ptr())
        };
    }
}

impl Hasher {
    /// Feeds `len` bytes of a Metal buffer, from `offset`, as [`update`]
    /// feeds host memory: any number of times, between host updates, in
    /// every mode, then finalize as usual. A shared buffer is host memory the
    /// GPU reads, split between the CPU and the GPU like [`Memory`]; a
    /// private one is hashed on the GPU. `false` when the backend cannot read
    /// it (no Metal, a bad range), with the hasher unchanged.
    ///
    /// # Safety
    ///
    /// `buffer` is an `id<MTLBuffer>` (as a pointer), alive for the call, of
    /// at least `offset + len` bytes, not written to during it.
    ///
    /// [`update`]: Hasher::update
    pub unsafe fn update_metal(&mut self, buffer: *mut c_void, offset: usize, len: usize) -> bool {
        if len == 0 {
            return true;
        }
        #[cfg(turboblake_gpu)]
        {
            if buffer.is_null() || backend() != Some(Backend::Metal) {
                return false;
            }
            let mut have = 0u64;
            let p = unsafe { ffi::tbg_metal_contents(buffer, &mut have) };
            if !p.is_null() {
                if offset as u64 > have || len as u64 > have - offset as u64 {
                    return false;
                }
                let reg = unsafe { ffi::tbg_register_metal(buffer) } == 1;
                self.update(unsafe { core::slice::from_raw_parts(p.add(offset), len) });
                if reg {
                    unsafe { ffi::tbg_unregister(p) };
                }
                return true;
            }
            return self.update_device(ffi::METAL, buffer, offset as u64, len as u64, core::ptr::null_mut());
        }
        #[cfg(not(turboblake_gpu))]
        {
            let _ = (buffer, offset);
            false
        }
    }

    /// Feeds `len` bytes of CUDA device memory, as [`update`] feeds host
    /// memory: any number of times, between host updates, in every mode,
    /// then finalize as usual. The GPU hashes them on `stream` (a `CUstream`;
    /// null for the default stream), after the work queued there, in the
    /// context the pointer belongs to; the call returns when it is done.
    /// `false` when the backend cannot (no CUDA), with the hasher unchanged.
    ///
    /// # Safety
    ///
    /// `device_ptr` points to at least `len` bytes of device memory, not
    /// written to during the call; `stream` is null or a stream of its context.
    ///
    /// [`update`]: Hasher::update
    pub unsafe fn update_cuda(&mut self, device_ptr: u64, len: usize, stream: *mut c_void) -> bool {
        if len == 0 {
            return true;
        }
        #[cfg(turboblake_gpu)]
        {
            if device_ptr == 0 || backend() != Some(Backend::Cuda) {
                return false;
            }
            return self.update_device(ffi::CUDA, device_ptr as usize as *mut c_void, 0, len as u64, stream);
        }
        #[cfg(not(turboblake_gpu))]
        {
            let _ = (device_ptr, stream);
            false
        }
    }

    // Bytes of GPU memory through the CPU: copied, then a plain update.
    #[cfg(turboblake_gpu)]
    fn update_host(&mut self, kind: i32, obj: *mut c_void, off: u64, len: u64, stream: *mut c_void) -> bool {
        let mut buf = vec![0u8; len as usize];
        if unsafe { ffi::tbg_read(kind, obj, off, len, stream, buf.as_mut_ptr()) } != 1 {
            return false;
        }
        self.update(&buf);
        true
    }

    // A full chunk state with more input to come: its CV goes on the stack,
    // as update does when the next bytes arrive.
    #[cfg(turboblake_gpu)]
    fn flush_chunk(&mut self) {
        if self.chunk_state.count() == crate::CHUNK_LEN {
            let cv = self.chunk_state.output().chaining_value();
            self.push_cv(&cv, self.chunk_state.chunk_counter);
            self.chunk_state = crate::ChunkState::new(
                &self.key,
                self.chunk_state.chunk_counter + 1,
                self.chunk_state.flags,
                self.chunk_state.platform,
            );
        }
    }

    // update_with_join's loop over GPU memory: the bytes that finish a chunk,
    // and subtrees below tbg_dev_min(), go through the CPU; the rest are
    // subtrees the GPU hashes into the two CVs the loop would push.
    #[cfg(turboblake_gpu)]
    fn update_device(&mut self, kind: i32, obj: *mut c_void, mut off: u64, mut len: u64, stream: *mut c_void) -> bool {
        use crate::CHUNK_LEN;
        let saved = self.clone();
        let input_offset = self.initial_chunk_counter * CHUNK_LEN as u64;
        if let Some(max) = crate::hazmat::max_subtree_len(input_offset) {
            assert!(len <= max - self.count(), "the subtree is too long for its offset");
        }
        let small = unsafe { ffi::tbg_dev_min() };
        let ok = 'run: {
            if self.chunk_state.count() > 0 {
                let take = ((CHUNK_LEN - self.chunk_state.count()) as u64).min(len);
                if !self.update_host(kind, obj, off, take, stream) {
                    break 'run false;
                }
                off += take;
                len -= take;
            }
            while len > CHUNK_LEN as u64 {
                self.flush_chunk();
                let mut sub = crate::largest_power_of_two_leq(len as usize) as u64;
                let so_far = self.chunk_state.chunk_counter * CHUNK_LEN as u64;
                while (sub - 1) & so_far != 0 {
                    sub /= 2;
                }
                if sub < small || sub <= CHUNK_LEN as u64 {
                    // whole chunks: the update keeps the last one in the chunk state
                    if !self.update_host(kind, obj, off, sub, stream) {
                        break 'run false;
                    }
                } else {
                    let mut pair = [0u8; 64];
                    let ctr = self.chunk_state.chunk_counter;
                    let done = unsafe {
                        ffi::tbg_dev_subtree(
                            kind,
                            obj,
                            off,
                            sub,
                            stream,
                            self.key.as_ptr(),
                            ctr,
                            self.chunk_state.flags,
                            pair.as_mut_ptr(),
                        )
                    };
                    if done != 1 {
                        break 'run false;
                    }
                    let chunks = sub / CHUNK_LEN as u64;
                    self.push_cv(pair[..32].try_into().unwrap(), ctr);
                    self.push_cv(pair[32..].try_into().unwrap(), ctr + chunks / 2);
                    self.chunk_state.chunk_counter += chunks;
                }
                off += sub;
                len -= sub;
            }
            if len > 0 {
                self.flush_chunk();
                break 'run self.update_host(kind, obj, off, len, stream);
            }
            true
        };
        if !ok {
            *self = saved;
        }
        ok
    }
}

#[cfg(all(test, turboblake_gpu))]
mod tests {
    use super::*;

    fn pattern(n: usize) -> Vec<u8> {
        (0..n).map(|i| (i % 251) as u8).collect()
    }

    // GPU memory holding `data` after `pad` bytes; private on Metal unless shared.
    struct Dev(*mut c_void);
    impl Dev {
        fn new(data: &[u8], pad: usize, shared: bool) -> Self {
            let d = unsafe { ffi::tbg_upload(data.as_ptr(), data.len() as u64, pad as u64, !shared as i32) };
            assert!(!d.is_null());
            Dev(d)
        }
    }
    impl Drop for Dev {
        fn drop(&mut self) {
            unsafe { ffi::tbg_drop(self.0) };
        }
    }

    fn feed(h: &mut Hasher, dev: &Dev, data: &[u8], pad: usize, split: usize, mix: bool) {
        let mut at = 0;
        let mut k = 0;
        while at < data.len() {
            let n = if split == 0 { data.len() - at } else { split.min(data.len() - at) };
            if mix && k % 2 == 1 {
                h.update(&data[at..at + n]);
            } else {
                let ok = unsafe {
                    match backend() {
                        Some(Backend::Metal) => h.update_metal(dev.0, pad + at, n),
                        _ => h.update_cuda(dev.0 as usize as u64 + (pad + at) as u64, n, core::ptr::null_mut()),
                    }
                };
                assert!(ok, "GPU update of {} bytes at {}", n, at);
            }
            at += n;
            k += 1;
        }
    }

    // Every official vector in all three modes, extended output and a seek,
    // through GPU memory at an odd offset, alone and between host updates.
    #[test]
    fn test_gpu_vectors() {
        if backend().is_none() {
            return;
        }
        let key: [u8; 32] = *b"whats the Elvish word for friend";
        let context = "BLAKE3 2019-12-27 16:29:52 test vectors context";
        for &n in crate::test::TEST_CASES {
            let data = pattern(n);
            let shared = backend() == Some(Backend::Metal) && n % 2 == 0;
            let dev = Dev::new(&data, 5, shared);
            for (split, mix) in [(0, false), (1, true), (1025, true), (3000, false), (8192, true)] {
                for mut h in [Hasher::new(), Hasher::new_keyed(&key), Hasher::new_derive_key(context)] {
                    let mut want = h.clone();
                    want.update(&data);
                    feed(&mut h, &dev, &data, 5, split, mix);
                    let (mut a, mut b) = ([0u8; 131], [0u8; 131]);
                    want.finalize_xof().fill(&mut a);
                    h.finalize_xof().fill(&mut b);
                    assert_eq!(a, b, "len {} split {} mix {}", n, split, mix);
                    let (mut a, mut b) = ([0u8; 32], [0u8; 32]);
                    let mut x = want.finalize_xof();
                    x.set_position(7);
                    x.fill(&mut a);
                    let mut y = h.finalize_xof();
                    y.set_position(7);
                    y.fill(&mut b);
                    assert_eq!(a, b);
                }
            }
        }
    }

    // Subtrees far past 4 TiB (hazmat's input offsets): the GPU counts chunks
    // in 64 bits.
    #[test]
    fn test_gpu_high_counters() {
        use crate::hazmat::HasherExt;
        if backend().is_none() {
            return;
        }
        let data = pattern((1 << 20) + 3 * 1024 + 5);
        let dev = Dev::new(&data, 0, false);
        for offset in [1u64 << 42, 5 << 40, (1u64 << 52) + (1 << 30)] {
            let mut want = Hasher::new();
            want.set_input_offset(offset);
            want.update(&data);
            let mut got = Hasher::new();
            got.set_input_offset(offset);
            feed(&mut got, &dev, &data, 0, 0, false);
            assert_eq!(want.finalize_non_root(), got.finalize_non_root(), "offset {}", offset);
        }
    }

    // Random inputs across the GPU's edges, against the CPU's hash.
    #[test]
    fn test_gpu_random() {
        if backend().is_none() {
            return;
        }
        let mut x = 7u64;
        for &n in &[2048usize, 2049, 65536 + 1, 262144, 262144 + 1, (3 << 20) + 77, (16 << 20) + 1024] {
            let data: Vec<u8> = (0..n)
                .map(|_| {
                    x ^= x << 13;
                    x ^= x >> 7;
                    x ^= x << 17;
                    x as u8
                })
                .collect();
            let want = crate::hash(&data);
            for (pad, split, mix) in [(0, 0, false), (16, 1 << 20, false), (5, 1000, true)] {
                let dev = Dev::new(&data, pad, false);
                let mut h = Hasher::new();
                feed(&mut h, &dev, &data, pad, split, mix);
                assert_eq!(h.finalize(), want, "len {} pad {} split {}", n, pad, split);
            }
            if let Some(mut m) = Memory::new(n) {
                m.copy_from_slice(&data);
                assert_eq!(crate::hash(&m), want, "Memory, len {}", n);
                assert_eq!(Hasher::new().update(&m).finalize(), want);
            }
        }
    }
}
