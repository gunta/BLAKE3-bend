// Duo has no JavaScript lane: the two sides are native builds.
function duo_native_only() {
  throw new Error("Duo: build natively (bend/build.sh)");
}

io_eff(CID(Duo.open), duo_native_only);
io_eff(CID(Duo.ready), duo_native_only);
io_eff(CID(Duo.go), duo_native_only);
io_eff(CID(Duo.wait), duo_native_only);
io_eff(CID(Duo.put), duo_native_only);
io_eff(CID(Duo.done), duo_native_only);
io_eff(CID(Duo.await), duo_native_only);
io_eff(CID(Duo.get), duo_native_only);
