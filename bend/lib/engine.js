// The engine is a native library: there is no JavaScript lane for it.
function eng_native_only() {
  throw new Error("Eng: libturboblake's engine runs natively (bend/lib/build.sh)");
}

io_eff(CID(Eng.next), eng_native_only);
io_eff(CID(Eng.done), eng_native_only);
