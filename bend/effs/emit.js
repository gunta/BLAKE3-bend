// B3IO.emit has no JavaScript lane yet: b3sum is a native build.
function b3io_emit() {
  throw new Error("B3IO.emit: build b3sum natively (bend/build.sh bend/b3sum.bend)");
}

io_eff(CID(B3IO.emit), b3io_emit);

io_eff(CID(B3IO.fold), b3io_emit);
io_eff(CID(B3IO.give), b3io_emit);
