// Package blake3 is BLAKE3 for Go with the API of lukechampine.com/blake3,
// on libturboblake: the official BLAKE3 C library, whose big inputs are
// hashed on every core by a Bend2 engine. Swap the import path and keep the
// code:
//
//	import "github.com/gunta/turboblake/bend/go" // was lukechampine.com/blake3
//
// For the API of github.com/zeebo/blake3, import
// github.com/gunta/turboblake/bend/go/zeebo instead. Both need cgo (a C
// compiler) and run on macOS and Linux.
package blake3

/*
#cgo CFLAGS: -O3 -w -DTURBOBLAKE -DTURBOBLAKE_GPU
#cgo arm64 CFLAGS: -DBLAKE3_USE_NEON=1
#cgo !arm64,!amd64 CFLAGS: -DBLAKE3_NO_SSE2 -DBLAKE3_NO_SSE41 -DBLAKE3_NO_AVX2 -DBLAKE3_NO_AVX512
#cgo LDFLAGS: -lpthread -lm
#cgo linux LDFLAGS: -ldl
#include <stdint.h>
#include <stdlib.h>
#include "csrc/blake3.h"

int b3e_files(uint32_t n, const char* const* paths, unsigned char (*out)[32], int* err);
*/
import "C"

import (
	"errors"
	"io"
	"math"
	"os"
	"syscall"
	"unsafe"
)

// Hasher implements hash.Hash.
type Hasher struct {
	h    C.blake3_hasher
	size int
}

// New returns a Hasher for the specified digest size and key. If key is nil,
// the hash is unkeyed. Otherwise, len(key) must be 32.
func New(size int, key []byte) *Hasher {
	h := &Hasher{size: size}
	if key == nil {
		C.blake3_hasher_init(&h.h)
	} else {
		_ = key[31] // as upstream: a short key panics, extra bytes are ignored
		C.blake3_hasher_init_keyed(&h.h, (*C.uint8_t)(unsafe.Pointer(&key[0])))
	}
	return h
}

// NewDeriveKey returns a Hasher in BLAKE3's key derivation mode, for ctx
// (an addition to lukechampine.com/blake3's API; see DeriveKey).
func NewDeriveKey(size int, ctx string) *Hasher {
	h := &Hasher{size: size}
	C.blake3_hasher_init_derive_key_raw(&h.h, unsafe.Pointer(unsafe.StringData(ctx)), C.size_t(len(ctx)))
	return h
}

// Write implements hash.Hash.
func (h *Hasher) Write(p []byte) (int, error) {
	if len(p) > 0 {
		C.blake3_hasher_update(&h.h, unsafe.Pointer(&p[0]), C.size_t(len(p)))
	}
	return len(p), nil
}

// WriteString is Write, from a string.
func (h *Hasher) WriteString(s string) (int, error) {
	if len(s) > 0 {
		C.blake3_hasher_update(&h.h, unsafe.Pointer(unsafe.StringData(s)), C.size_t(len(s)))
	}
	return len(s), nil
}

// Sum implements hash.Hash.
func (h *Hasher) Sum(b []byte) (sum []byte) {
	out := make([]byte, h.size)
	if h.size > 0 {
		C.blake3_hasher_finalize(&h.h, (*C.uint8_t)(unsafe.Pointer(&out[0])), C.size_t(h.size))
	}
	return append(b, out...)
}

// Reset implements hash.Hash.
func (h *Hasher) Reset() { C.blake3_hasher_reset(&h.h) }

// Size implements hash.Hash.
func (h *Hasher) Size() int { return h.size }

// BlockSize implements hash.Hash.
func (h *Hasher) BlockSize() int { return 64 }

// Clone returns an independent copy of h (an addition to the upstream API).
func (h *Hasher) Clone() *Hasher {
	c := *h
	return &c
}

// XOF returns an OutputReader initialized with the current hash state.
func (h *Hasher) XOF() *OutputReader {
	return &OutputReader{h: h.h}
}

// An OutputReader produces an seekable stream of 2^64 - 1 pseudorandom output
// bytes.
type OutputReader struct {
	h   C.blake3_hasher
	off uint64
}

// Read implements io.Reader. Callers may assume that Read returns len(p),
// nil unless the read would extend beyond the end of the stream.
func (or *OutputReader) Read(p []byte) (int, error) {
	if or.off == math.MaxUint64 {
		return 0, io.EOF
	} else if rem := math.MaxUint64 - or.off; uint64(len(p)) > rem {
		p = p[:rem]
	}
	if len(p) > 0 {
		C.blake3_hasher_finalize_seek(&or.h, C.uint64_t(or.off), (*C.uint8_t)(unsafe.Pointer(&p[0])), C.size_t(len(p)))
	}
	or.off += uint64(len(p))
	return len(p), nil
}

// Seek implements io.Seeker.
func (or *OutputReader) Seek(offset int64, whence int) (int64, error) {
	off := or.off
	switch whence {
	case io.SeekStart:
		if offset < 0 {
			return 0, errors.New("seek position cannot be negative")
		}
		off = uint64(offset)
	case io.SeekCurrent:
		if offset < 0 {
			if uint64(-offset) > off {
				return 0, errors.New("seek position cannot be negative")
			}
			off -= uint64(-offset)
		} else {
			off += uint64(offset)
		}
	case io.SeekEnd:
		off = uint64(offset) - 1
	default:
		panic("invalid whence")
	}
	or.off = off
	return int64(or.off), nil
}

func sum(b []byte, out []byte) {
	var h C.blake3_hasher
	C.blake3_hasher_init(&h)
	if len(b) > 0 {
		C.blake3_hasher_update(&h, unsafe.Pointer(&b[0]), C.size_t(len(b)))
	}
	C.blake3_hasher_finalize(&h, (*C.uint8_t)(unsafe.Pointer(&out[0])), C.size_t(len(out)))
}

// Sum256 returns the unkeyed BLAKE3 hash of b, truncated to 256 bits.
func Sum256(b []byte) (out [32]byte) {
	sum(b, out[:])
	return
}

// Sum512 returns the unkeyed BLAKE3 hash of b, truncated to 512 bits.
func Sum512(b []byte) (out [64]byte) {
	sum(b, out[:])
	return
}

// DeriveKey derives a subkey from ctx and srcKey. ctx should be hardcoded,
// globally unique, and application-specific. A good format for ctx strings is:
//
//	[application] [commit timestamp] [purpose]
//
// e.g.:
//
//	example.com 2019-12-25 16:18:03 session tokens v1
//
// The purpose of these requirements is to ensure that an attacker cannot trick
// two different applications into using the same context string.
func DeriveKey(subKey []byte, ctx string, srcKey []byte) {
	h := NewDeriveKey(0, ctx)
	h.Write(srcKey)
	h.XOF().Read(subKey)
}

// HashFiles hashes many files at once, as the turboblake command does: opened,
// mapped or read in parallel, files not in the page cache streamed at SSD
// speed, every file's tree on every core. For each path, its BLAKE3 hash or
// the error reading it (a pipe or device is read with a Hasher instead).
// An addition to the upstream API.
func HashFiles(paths []string) ([][32]byte, []error) {
	n := len(paths)
	sums := make([][32]byte, n)
	errs := make([]error, n)
	if n == 0 {
		return sums, errs
	}
	cs := make([]*C.char, n)
	for i, p := range paths {
		cs[i] = C.CString(p)
	}
	defer func() {
		for _, c := range cs {
			C.free(unsafe.Pointer(c))
		}
	}()
	out := (*[1 << 30][32]C.uchar)(C.malloc(C.size_t(n) * 32))[:n:n]
	codes := (*[1 << 30]C.int)(C.malloc(C.size_t(n) * C.sizeof_int))[:n:n]
	defer C.free(unsafe.Pointer(&out[0]))
	defer C.free(unsafe.Pointer(&codes[0]))
	ok := C.b3e_files(C.uint32_t(n), (**C.char)(unsafe.Pointer(&cs[0])), (*[32]C.uchar)(unsafe.Pointer(&out[0])), &codes[0]) == 1
	for i := range paths {
		switch {
		case ok && codes[i] == 0:
			sums[i] = *(*[32]byte)(unsafe.Pointer(&out[i]))
		case ok && codes[i] != -1:
			errs[i] = &os.PathError{Op: "open", Path: paths[i], Err: syscall.Errno(codes[i])}
		default:
			sums[i], errs[i] = hashReader(paths[i])
		}
	}
	return sums, errs
}

func hashReader(path string) (sum [32]byte, err error) {
	f, err := os.Open(path)
	if err != nil {
		return sum, err
	}
	defer f.Close()
	h := New(32, nil)
	if _, err = io.Copy(h, f); err == nil {
		copy(sum[:], h.Sum(nil))
	}
	return sum, err
}
