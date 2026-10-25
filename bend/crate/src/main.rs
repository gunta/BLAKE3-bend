//! `b3sum-bend`: the Bend2 b3sum. All of it, the runtime included, is the C
//! that Bend emits for `bend/b3sum.bend` (see build.rs); this only passes the
//! command line to Bend's `main`, which takes `+RTS ... -RTS` options too
//! (`+RTS --threads N -RTS`).

use std::ffi::{CString, c_char, c_int};
use std::os::unix::ffi::OsStringExt;

unsafe extern "C" {
    fn bend_b3sum_main(argc: c_int, argv: *const *const c_char) -> c_int;
}

fn main() {
    let args: Vec<CString> = std::env::args_os()
        .map(|a| CString::new(a.into_vec()).expect("an argument with a NUL byte"))
        .collect();
    let mut argv: Vec<*const c_char> = args.iter().map(|a| a.as_ptr()).collect();
    argv.push(std::ptr::null());
    let code = unsafe { bend_b3sum_main(args.len() as c_int, argv.as_ptr()) };
    std::process::exit(code);
}
