// turboblake for Go against Go's BLAKE3s (lukechampine.com/blake3,
// github.com/zeebo/blake3) and its other hashes, in memory, one-shot,
// interleaved; medians in ms. Writes bend/bench/results/lang-go.json.
//
//	go run .
package main

import (
	"crypto/md5"
	"crypto/sha1"
	"crypto/sha256"
	"crypto/sha3"
	"crypto/sha512"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"sort"
	"strings"
	"time"

	b3 "github.com/gunta/turboblake/bend/go"
	zeebo "github.com/zeebo/blake3"
	"golang.org/x/crypto/blake2b"
	"golang.org/x/crypto/blake2s"
	luke "lukechampine.com/blake3"
)

type side struct {
	name string
	f    func([]byte) []byte
}

func main() {
	sizes := []int{1 << 10, 64 << 10, 1 << 20, 16 << 20, 256 << 20, 1 << 30}
	data := make([]byte, 1<<30)
	for i := range data {
		data[i] = byte(uint32(i) * 2654435761 >> 13)
	}
	sides := []side{
		{"turboblake", func(b []byte) []byte { s := b3.Sum256(b); return s[:] }},
		{"lukechampine.com/blake3", func(b []byte) []byte { s := luke.Sum256(b); return s[:] }},
		{"github.com/zeebo/blake3", func(b []byte) []byte { s := zeebo.Sum256(b); return s[:] }},
		{"crypto/sha256", func(b []byte) []byte { s := sha256.Sum256(b); return s[:] }},
		{"crypto/sha512", func(b []byte) []byte { s := sha512.Sum512(b); return s[:] }},
		{"crypto/sha1", func(b []byte) []byte { s := sha1.Sum(b); return s[:] }},
		{"crypto/md5", func(b []byte) []byte { s := md5.Sum(b); return s[:] }},
		{"x/crypto/blake2b", func(b []byte) []byte { s := blake2b.Sum512(b); return s[:] }},
		{"x/crypto/blake2s", func(b []byte) []byte { s := blake2s.Sum256(b); return s[:] }},
		{"crypto/sha3 (256)", func(b []byte) []byte { s := sha3.Sum256(b); return s[:] }},
	}
	type row struct {
		Impl   string  `json:"impl"`
		Bytes  int     `json:"bytes"`
		Ms     float64 `json:"ms"`
		Digest string  `json:"digest"`
	}
	var rows []row
	agree := true
	for _, n := range sizes {
		b := data[:n]
		reps := 30
		if n > 1<<20 {
			reps = 9
		}
		if n > 64<<20 {
			reps = 3
		}
		times := make([][]float64, len(sides))
		digests := make([]string, len(sides))
		for i, s := range sides {
			digests[i] = hex.EncodeToString(s.f(b))[:16]
		}
		for r := 0; r < reps; r++ {
			for i, s := range sides {
				t := time.Now()
				s.f(b)
				times[i] = append(times[i], float64(time.Since(t).Nanoseconds())/1e6)
			}
		}
		for i, s := range sides {
			sort.Float64s(times[i])
			rows = append(rows, row{s.name, n, times[i][len(times[i])/2], digests[i]})
		}
		agree = agree && digests[0] == digests[1] && digests[0] == digests[2]
	}
	fmt.Printf("%s %s/%s, %d CPUs\n\n| bytes |", runtime.Version(), runtime.GOOS, runtime.GOARCH, runtime.NumCPU())
	for _, s := range sides {
		fmt.Printf(" %s |", s.name)
	}
	fmt.Printf("\n|---:|%s\n", strings.Repeat("---:|", len(sides)))
	for _, n := range sizes {
		size := fmt.Sprintf("%d KiB", n>>10)
		if n >= 1<<30 {
			size = fmt.Sprintf("%d GiB", n>>30)
		} else if n >= 1<<20 {
			size = fmt.Sprintf("%d MiB", n>>20)
		}
		fmt.Printf("| %s |", size)
		for _, r := range rows {
			if r.Bytes == n {
				fmt.Printf(" %.3f ms |", r.Ms)
			}
		}
		fmt.Println()
	}
	fmt.Printf("\nBLAKE3 digests agree: %v\n", agree)
	out, _ := json.MarshalIndent(map[string]any{
		"info": map[string]any{"go": runtime.Version(), "goos": runtime.GOOS, "goarch": runtime.GOARCH,
			"cpus": runtime.NumCPU(), "digests_agree": agree},
		"rows": rows,
	}, "", "  ")
	os.WriteFile("../../bench/results/lang-go.json", append(out, '\n'), 0o644)
	fmt.Println("wrote bend/bench/results/lang-go.json")
}
