// B3IO.load has no JavaScript lane yet: b3sum is a native build.
function b3io_load() {
  throw new Error("B3IO.load: build b3sum natively (bend/build.sh bend/b3sum.bend)");
}

io_eff(CID(B3IO.load), b3io_load);
