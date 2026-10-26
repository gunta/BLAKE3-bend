#!/usr/bin/env python3
"""The two source patches libturboblake needs, each checked to apply.

  patch.py hook   <blake3.c>   the subtree hook in the official C library
  patch.py embed  <engine.c>   Bend's emitted C, made fit to run inside
                               another program: no process-wide signal
                               handlers (a host such as V8 or Go owns those)
"""
import sys

HOOK_DECL = (
    '#include "blake3_impl.h"\n',
    '#include "blake3_impl.h"\n'
    '#if defined(TURBOBLAKE)\n'
    '#include "turboblake.h"\n'
    '#endif\n',
)

HOOK_CALL = (
    '#if defined(BLAKE3_TESTING)\n'
    '  assert(input_len > BLAKE3_CHUNK_LEN);\n'
    '#endif\n'
    '\n'
    '  uint8_t cv_array[MAX_SIMD_DEGREE_OR_2 * BLAKE3_OUT_LEN];\n',
    '#if defined(BLAKE3_TESTING)\n'
    '  assert(input_len > BLAKE3_CHUNK_LEN);\n'
    '#endif\n'
    '\n'
    '#if defined(TURBOBLAKE)\n'
    '  // libturboblake: a big subtree goes to the Bend engine, all cores\n'
    '  if (turboblake_subtree(input, input_len, key, chunk_counter, flags, out)) {\n'
    '    return;\n'
    '  }\n'
    '#endif\n'
    '\n'
    '  uint8_t cv_array[MAX_SIMD_DEGREE_OR_2 * BLAKE3_OUT_LEN];\n',
)

EMBED = [
    # pool_stack: the SIGSEGV/SIGBUS trap that reports a stack overflow
    ('  sigaction(SIGSEGV, &sa, NULL);\n  sigaction(SIGBUS, &sa, NULL);\n',
     '#ifndef BEND_EMBED\n  sigaction(SIGSEGV, &sa, NULL);\n  sigaction(SIGBUS, &sa, NULL);\n#endif\n'),
    # io_loop: SIGPIPE ignored process-wide
    ('  io_stk = pool_stack();\n  signal(SIGPIPE, SIG_IGN);\n',
     '  io_stk = pool_stack();\n#ifndef BEND_EMBED\n  signal(SIGPIPE, SIG_IGN);\n#endif\n'),
    # corpus_at: inside the room engine.c reserved on macOS (b3e_reserve), a
    # map replaces the reservation (MAP_FIXED); a hint never lands there
    ('static bool corpus_at(void* at, u64 size) {\n',
     'static bool corpus_at(void* at, u64 size) {\n'
     '#if defined(BEND_EMBED) && defined(__APPLE__)\n'
     '  extern char* b3e_resv;\n'
     '  extern u64 b3e_resv_len;\n'
     '  if (b3e_resv != NULL && (char*)at >= b3e_resv && (char*)at + size <= b3e_resv + b3e_resv_len) {\n'
     '    return mmap(at, size, PROT_READ | PROT_WRITE,\n'
     '      MAP_PRIVATE | MAP_ANON | MAP_NORESERVE | MAP_FIXED, -1, 0) == at;\n'
     '  }\n'
     '#endif\n'),
    # corpus_map: on macOS, the heap goes in that room; elsewhere, a few TiB
    # below the first big input the engine sees (engine.c's b3e_hint), so the
    # 8 TiB a Term can name cover the host's memory and the engine reads it
    # where it lies; else, on Linux, 7 TiB below where mmap hands out memory
    # (malloc maps big buffers there); or at B3E_HEAP_AT, if the build fixes it
    ('static void* corpus_map(u64 size) {\n',
     'static void* corpus_map(u64 size) {\n'
     '#if defined(BEND_EMBED) && defined(__APPLE__)\n'
     '  extern char* b3e_resv;\n'
     '  if (b3e_resv != NULL && corpus_at(b3e_resv, size)) {\n'
     '    return b3e_resv;\n'
     '  }\n'
     '#endif\n'
     '#if defined(BEND_EMBED) && defined(B3E_HEAP_AT)\n'
     '  if (corpus_at((void*)(uintptr_t)(B3E_HEAP_AT), size)) {\n'
     '    return (void*)(uintptr_t)(B3E_HEAP_AT);\n'
     '  }\n'
     '#endif\n'
     '#if defined(BEND_EMBED)\n'
     '  extern uintptr_t b3e_hint;\n'
     '  u64 near = (u64)b3e_hint & ~((1ull << 30) - 1);\n'
     '  for (u32 d = 0; near != 0 && d < 6; d += 1) {\n'
     '    u64 back = (u64[]){ 4, 2, 6, 1, 3, 5 }[d] << 40;\n'
     '    if (near > back + (1ull << 40) && corpus_at((void*)(uintptr_t)(near - back), size)) {\n'
     '      return (void*)(uintptr_t)(near - back);\n'
     '    }\n'
     '  }\n'
     '#endif\n'
     '#if defined(BEND_EMBED) && defined(__linux__)\n'
     '  void* probe = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);\n'
     '  if (probe != MAP_FAILED) {\n'
     '    u64 top = (u64)(uintptr_t)probe & ~((1ull << 30) - 1);\n'
     '    munmap(probe, 4096);\n'
     '    if (top > (8ull << 40) && corpus_at((void*)(uintptr_t)(top - (7ull << 40)), size)) {\n'
     '      return (void*)(uintptr_t)(top - (7ull << 40));\n'
     '    }\n'
     '  }\n'
     '#endif\n'),
]


def apply(path, pairs):
    s = open(path).read()
    for old, new in pairs:
        if s.count(old) != 1:
            sys.exit(f"patch.py: {path}: anchor not found once:\n{old}")
        s = s.replace(old, new)
    open(path, "w").write(s)


if __name__ == "__main__":
    what, path = sys.argv[1], sys.argv[2]
    apply(path, {"hook": [HOOK_DECL, HOOK_CALL], "embed": EMBED}[what])
