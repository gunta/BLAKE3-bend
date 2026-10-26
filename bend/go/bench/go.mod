module github.com/gunta/BLAKE3-bend/bend/go/bench

go 1.26.0

replace github.com/gunta/BLAKE3-bend/bend/go => ../

require (
	github.com/gunta/BLAKE3-bend/bend/go v0.0.0-00010101000000-000000000000
	github.com/zeebo/blake3 v0.2.4
	golang.org/x/crypto v0.58.0
	lukechampine.com/blake3 v1.4.1
)

require (
	github.com/klauspost/cpuid/v2 v2.0.12 // indirect
	golang.org/x/sys v0.49.0 // indirect
)
