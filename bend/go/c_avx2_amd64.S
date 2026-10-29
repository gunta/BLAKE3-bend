#if defined(_WIN32)
#include "csrc/blake3_avx2_x86-64_windows_gnu.S"
#else
#include "csrc/blake3_avx2_x86-64_unix.S"
#endif
