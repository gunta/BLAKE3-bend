#!/usr/bin/env python3
"""The two source patches libblake3-bend needs, each checked to apply.

  patch.py hook   <blake3.c>   the subtree hook in the official C library
  patch.py embed  <engine.c>   Bend's emitted C, made fit to run inside
                               another program: no process-wide signal
                               handlers (a host such as V8 or Go owns those)
"""
import sys

HOOK_DECL = (
    '#include "blake3_impl.h"\n',
    '#include "blake3_impl.h"\n'
    '#if defined(BLAKE3_BEND)\n'
    '#include "blake3_bend.h"\n'
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
    '#if defined(BLAKE3_BEND)\n'
    '  // libblake3-bend: a big subtree goes to the Bend engine, all cores\n'
    '  if (blake3_bend_subtree(input, input_len, key, chunk_counter, flags, out)) {\n'
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
    # corpus_map: on Linux, put the heap 7 TiB below where mmap hands out
    # memory, so the 8 TiB a Term can name cover the host's big buffers
    # (malloc maps them there) and the engine reads them with no copy
    ('static void* corpus_map(u64 size) {\n',
     'static void* corpus_map(u64 size) {\n'
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
