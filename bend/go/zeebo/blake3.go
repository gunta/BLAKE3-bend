// Package blake3 is BLAKE3 for Go with the API of github.com/zeebo/blake3,
// on libblake3-bend (see the parent package). Swap the import path:
//
//	import "github.com/gunta/BLAKE3-bend/bend/go/zeebo" // was github.com/zeebo/blake3
package blake3

import (
	"errors"
	"fmt"
	"io"

	core "github.com/gunta/BLAKE3-bend/bend/go"
)

// Hasher is a hash.Hash for BLAKE3.
type Hasher struct {
	h *core.Hasher
}

// New returns a new Hasher that has a digest size of 32 bytes.
func New() *Hasher { return &Hasher{core.New(32, nil)} }

// NewKeyed returns a new Hasher that uses the 32 byte input key and has a
// digest size of 32 bytes.
func NewKeyed(key []byte) (*Hasher, error) {
	if len(key) != 32 {
		return nil, errors.New("invalid key size")
	}
	return &Hasher{core.New(32, key)}, nil
}

// NewDeriveKey returns a Hasher that is initialized with the context string.
// It has a digest size of 32 bytes.
func NewDeriveKey(context string) *Hasher { return &Hasher{core.NewDeriveKey(32, context)} }

// Write implements part of the hash.Hash interface.
func (h *Hasher) Write(p []byte) (int, error) { return h.h.Write(p) }

// WriteString is Write, from a string.
func (h *Hasher) WriteString(p string) (int, error) { return h.h.WriteString(p) }

// Reset implements part of the hash.Hash interface.
func (h *Hasher) Reset() { h.h.Reset() }

// Size implements part of the hash.Hash interface: 32.
func (h *Hasher) Size() int { return 32 }

// BlockSize implements part of the hash.Hash interface: 64.
func (h *Hasher) BlockSize() int { return 64 }

// Sum implements part of the hash.Hash interface. It appends the digest of the
// Hasher to the provided buffer and returns it.
func (h *Hasher) Sum(b []byte) []byte { return h.h.Sum(b) }

// Clone returns a new Hasher with the same internal state.
func (h *Hasher) Clone() *Hasher { return &Hasher{h.h.Clone()} }

// Digest takes a snapshot of the hash state and returns an object that can be
// used to read and seek through 2^64 bytes of digest output.
func (h *Hasher) Digest() *Digest { return &Digest{r: h.h.XOF()} }

// Digest captures the state of a Hasher allowing reading and seeking through
// the output stream.
type Digest struct {
	r   *core.OutputReader
	pos int64
}

// Read reads data from the hasher into out. It always fills the entire buffer.
func (d *Digest) Read(p []byte) (n int, err error) {
	n, err = d.r.Read(p)
	d.pos += int64(n)
	return n, err
}

// Seek sets the position to the provided location. Only SeekStart and
// SeekCurrent are allowed.
func (d *Digest) Seek(offset int64, whence int) (int64, error) {
	switch whence {
	case io.SeekStart:
	case io.SeekEnd:
		return 0, fmt.Errorf("seek from end not supported")
	case io.SeekCurrent:
		offset += d.pos
	default:
		return 0, fmt.Errorf("invalid whence: %d", whence)
	}
	if offset < 0 {
		return 0, fmt.Errorf("seek before start")
	}
	d.pos = offset
	return d.r.Seek(offset, io.SeekStart)
}

// Sum256 returns the first 256 bits of the unkeyed digest of the data.
func Sum256(data []byte) [32]byte { return core.Sum256(data) }

// Sum512 returns the first 512 bits of the unkeyed digest of the data.
func Sum512(data []byte) [64]byte { return core.Sum512(data) }

// DeriveKey derives a key based on reusable key material of any length, in
// the given context. The key will be stored in out, using all of its current
// length.
func DeriveKey(context string, material []byte, out []byte) {
	h := NewDeriveKey(context)
	_, _ = h.Write(material)
	_, _ = h.Digest().Read(out)
}
