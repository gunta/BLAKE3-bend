#!/bin/sh
# Builds the native CUDA reference with nvcc (CUDA 12+):
#   bend/ref/cuda/build.sh [out]
# On a machine with no CUDA, `build.sh --ptx` still compiles the kernels
# (b3.cu) to PTX with an LLVM clang that has the NVPTX backend, over a few
# stand-ins for the CUDA headers: a compile check, not a run.
set -e
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$here/build"
if [ "$1" = "--ptx" ]; then
  CLANG="${CLANG:-/opt/homebrew/opt/llvm/bin/clang}"
  cat > "$here/build/cuda_stub.h" <<'EOF'
// Stand-ins for the CUDA headers, enough to compile b3.cu to PTX.
#define __global__ __attribute__((global))
#define __device__ __attribute__((device))
#define __forceinline__ __inline__ __attribute__((always_inline))
struct __attribute__((aligned(16))) uint4 { unsigned x, y, z, w; };
struct Dim3 { unsigned x, y, z; };
struct TidX { __device__ operator unsigned() const { return __nvvm_read_ptx_sreg_tid_x(); } };
struct CtaX { __device__ operator unsigned() const { return __nvvm_read_ptx_sreg_ctaid_x(); } };
struct NtidX { __device__ operator unsigned() const { return __nvvm_read_ptx_sreg_ntid_x(); } };
static __device__ const struct { TidX x; } threadIdx = {};
static __device__ const struct { CtaX x; } blockIdx = {};
static __device__ const struct { NtidX x; } blockDim = {};
static __device__ __forceinline__ uint4 __ldg(const uint4 *p) { return *p; }
static __device__ __forceinline__ unsigned __shfl_down_sync(unsigned m, unsigned v, unsigned d) {
  return (unsigned)__nvvm_shfl_sync_down_i32(m, (int)v, (int)d, 0x1f);
}
static __device__ __forceinline__ unsigned __funnelshift_r(unsigned lo, unsigned hi, unsigned s) {
  return (lo >> (s & 31)) | (hi << ((32 - s) & 31));
}
static __device__ __forceinline__ unsigned min(unsigned a, unsigned b) { return a < b ? a : b; }
static __device__ __forceinline__ unsigned max(unsigned a, unsigned b) { return a > b ? a : b; }
EOF
  "$CLANG" -x cuda --cuda-device-only --cuda-gpu-arch=sm_80 -nocudainc -nocudalib \
    -Xclang -target-feature -Xclang +ptx70 -O3 -S -include "$here/build/cuda_stub.h" "$here/b3.cu" -o "$here/build/b3.ptx"
  echo "compiled $here/build/b3.ptx ($(grep -c '^.visible .entry' "$here/build/b3.ptx") kernels)"
  exit 0
fi
out="${1:-$here/build/b3cuda}"
nvcc -O3 -arch=native -std=c++17 "$here/b3cuda.cu" -o "$out"
echo "built $out"
