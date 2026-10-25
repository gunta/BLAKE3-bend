// B3IO.load has no JavaScript lane yet: b3sum is a native build.
function b3io_load() {
  throw new Error("B3IO.load: build b3sum natively (bend/build.sh bend/b3sum.bend)");
}

io_eff(CID(B3IO.load), b3io_load);

function b3io_native_only() {
  throw new Error("B3IO: build natively (bend/build.sh)");
}

io_eff(CID(B3IO.keep), b3io_native_only);
io_eff(CID(B3IO.again), b3io_native_only);
io_eff(CID(B3IO.release), b3io_native_only);
io_eff(CID(B3IO.seg), b3io_native_only);
