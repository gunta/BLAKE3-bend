// libturboblake's GPU backend (ADR 0017): loads Metal or CUDA at run time.
#if !defined(_WIN32)  // no engine on Windows (ADR 0020)
#include "csrc/turboblake_gpu.c"
#endif
