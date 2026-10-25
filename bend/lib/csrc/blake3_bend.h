// libblake3-bend: the official BLAKE3 C API (blake3.h), with big subtrees
// hashed by the Bend engine. These two calls are the only additions.
#ifndef BLAKE3_BEND_H
#define BLAKE3_BEND_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// The two CVs of a complete subtree of input_len bytes (a power of two of
// 2+ chunks), hashed by the engine; 0 when the C library should hash it.
// blake3.c calls this; callers of blake3.h never need to.
int blake3_bend_subtree(const uint8_t *input, size_t input_len, const uint32_t key[8],
                        uint64_t chunk_counter, uint8_t flags, uint8_t out[64]);

// 1 once the engine has started (it starts on the first big update).
int blake3_bend_running(void);

#ifdef __cplusplus
}
#endif

#endif
