package blake3_test

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"math/rand"
	"os"
	"path/filepath"
	"testing"

	b3 "github.com/gunta/turboblake/bend/go"
	zb "github.com/gunta/turboblake/bend/go/zeebo"
	luke "lukechampine.com/blake3"
	zeebo "github.com/zeebo/blake3"
)

var vectors struct {
	Key   string
	Ctx   string `json:"context_string"`
	Cases []struct {
		InputLen  int    `json:"input_len"`
		Hash      string `json:"hash"`
		KeyedHash string `json:"keyed_hash"`
		DeriveKey string `json:"derive_key"`
	}
}

func init() {
	data, err := os.ReadFile("testdata/vectors.json")
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(data, &vectors); err != nil {
		panic(err)
	}
}

func pattern(n int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte(i % 251)
	}
	return b
}

func TestVectors(t *testing.T) {
	for _, c := range vectors.Cases {
		in := pattern(c.InputLen)
		full := len(c.Hash) / 2
		for _, split := range []int{0, 1, 1023, 1024, 4097} {
			for _, m := range []struct {
				h    *b3.Hasher
				want string
			}{
				{b3.New(full, nil), c.Hash},
				{b3.New(full, []byte(vectors.Key)), c.KeyedHash},
				{b3.NewDeriveKey(full, vectors.Ctx), c.DeriveKey},
			} {
				for i := 0; i < len(in); {
					n := len(in) - i
					if split > 0 && n > split {
						n = split
					}
					m.h.Write(in[i : i+n])
					i += n
				}
				if got := hex.EncodeToString(m.h.Sum(nil)); got != m.want {
					t.Fatalf("len %d split %d: got %s want %s", c.InputLen, split, got, m.want)
				}
				out := make([]byte, full-5)
				x := m.h.XOF()
				x.Seek(5, io.SeekStart)
				x.Read(out)
				if hex.EncodeToString(out) != m.want[10:] {
					t.Fatalf("xof seek len %d", c.InputLen)
				}
			}
		}
		sub := make([]byte, full)
		b3.DeriveKey(sub, vectors.Ctx, in)
		if hex.EncodeToString(sub) != c.DeriveKey {
			t.Fatalf("DeriveKey len %d", c.InputLen)
		}
		if s := b3.Sum256(in); hex.EncodeToString(s[:]) != c.Hash[:64] {
			t.Fatalf("Sum256 len %d", c.InputLen)
		}
	}
}

// Against lukechampine.com/blake3 and github.com/zeebo/blake3, on random inputs.
func TestReferences(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	big := make([]byte, 64<<20+1)
	rng.Read(big)
	key := make([]byte, 32)
	rng.Read(key)
	for _, n := range []int{0, 1, 1025, 65536, 262145, 1 << 20, 3<<20 + 77, 16 << 20, 64<<20 + 1} {
		in := big[:n]
		if a, b := b3.Sum512(in), luke.Sum512(in); a != b {
			t.Fatalf("Sum512 %d", n)
		}
		h, l := b3.New(48, key), luke.New(48, key)
		h.Write(in)
		l.Write(in)
		if !bytes.Equal(h.Sum(nil), l.Sum(nil)) {
			t.Fatalf("keyed %d", n)
		}
		// lukechampine.com/blake3 v1.4.1 reads the wrong bytes after a Seek
		// to an offset that is not a multiple of 1024 (it fills its buffer
		// from the seek's block but indexes it from the 1 KiB boundary); the
		// official crate agrees with this package there. Compare at 1024.
		ho, lo := make([]byte, 333), make([]byte, 333)
		hx, lx := h.XOF(), l.XOF()
		hx.Seek(1024, io.SeekStart)
		lx.Seek(1024, io.SeekStart)
		hx.Read(ho)
		lx.Read(lo)
		if !bytes.Equal(ho, lo) {
			t.Fatalf("xof %d", n)
		}
		zh, zz := zb.NewDeriveKey("ctx"), zeebo.NewDeriveKey("ctx")
		zh.Write(in)
		zz.Write(in)
		zo, zr := make([]byte, 100), make([]byte, 100)
		zd, zrd := zh.Digest(), zz.Digest()
		zd.Seek(37, io.SeekStart)
		zrd.Seek(37, io.SeekStart)
		zd.Read(zo)
		zrd.Read(zr)
		if !bytes.Equal(zo, zr) || !bytes.Equal(zh.Clone().Sum(nil), zz.Sum(nil)) {
			t.Fatalf("zeebo derive %d", n)
		}
	}
	if _, err := zb.NewKeyed(key[:31]); err == nil {
		t.Fatal("NewKeyed takes 32 bytes")
	}
}

func TestHashFiles(t *testing.T) {
	dir := t.TempDir()
	var paths []string
	for i, n := range []int{0, 1, 1025, 1 << 20, 5<<20 + 3} {
		p := filepath.Join(dir, "f"+string(rune('a'+i)))
		os.WriteFile(p, pattern(n), 0o644)
		paths = append(paths, p)
	}
	sums, errs := b3.HashFiles(append(paths, filepath.Join(dir, "missing"), dir))
	for i, p := range paths {
		data, _ := os.ReadFile(p)
		if errs[i] != nil || sums[i] != luke.Sum256(data) {
			t.Fatalf("%s: %v", p, errs[i])
		}
	}
	if !errors.Is(errs[len(paths)], fs.ErrNotExist) || errs[len(paths)+1] == nil {
		t.Fatalf("errors: %v, %v", errs[len(paths)], errs[len(paths)+1])
	}
}
