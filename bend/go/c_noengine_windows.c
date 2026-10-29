// No engine on Windows yet (ADR 0020): the module is the official C there,
// and HashFiles reads every file with a Hasher.
#include <stdint.h>

int b3e_files(uint32_t n, const char* const* paths, unsigned char (*out)[32], int* err) {
  (void)n, (void)paths, (void)out, (void)err;
  return 0;
}
