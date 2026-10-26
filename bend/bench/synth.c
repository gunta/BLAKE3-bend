// Writes a stand-in for a model shard: a safetensors file of exactly
// <bytes> bytes (8-byte header length, a JSON header naming BF16 tensors,
// then the tensor bytes), filled by a seeded PRNG, so a benchmark host can
// make DeepSeek-sized inputs in seconds instead of downloading them.
// The bytes depend only on (bytes, seed): two runs write the same file.
//   cc -O3 -pthread -o synth synth.c && ./synth out.safetensors 101537926640 48
// usage: synth <path> <bytes> <seed> [threads]
#define _GNU_SOURCE
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define BLK (8u << 20)

static int fd;
static uint64_t total, data_at, seed, nblk;
static uint64_t next_blk;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

// wyrand: one multiply per 8 bytes.
static inline uint64_t wy(uint64_t* s) {
  *s += 0xa0761d6478bd642full;
  __uint128_t m = (__uint128_t)*s * (*s ^ 0xe7037ed1a0b428dbull);
  return (uint64_t)(m >> 64) ^ (uint64_t)m;
}

static void* writer(void* arg) {
  (void)arg;
  uint64_t* buf = aligned_alloc(4096, BLK);
  for (;;) {
    pthread_mutex_lock(&lock);
    uint64_t b = next_blk++;
    pthread_mutex_unlock(&lock);
    if (b >= nblk) break;
    uint64_t off = data_at + b * BLK, len = total - off < BLK ? total - off : BLK;
    uint64_t s = seed * 0x9e3779b97f4a7c15ull ^ b;
    for (uint64_t i = 0; i < (len + 7) / 8; i++) buf[i] = wy(&s);
    for (uint64_t got = 0; got < len;) {
      ssize_t n = pwrite(fd, (char*)buf + got, len - got, (off_t)(off + got));
      if (n <= 0) { perror("pwrite"); exit(1); }
      got += (uint64_t)n;
    }
  }
  free(buf);
  return NULL;
}

int main(int argc, char** argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: synth <path> <bytes> <seed> [threads]\n");
    return 2;
  }
  total = strtoull(argv[2], NULL, 10);
  seed = strtoull(argv[3], NULL, 10);
  int threads = argc > 4 ? atoi(argv[4]) : 16;
  // The header: tensors of 5120 x 9216 BF16 (94 MB each, as DeepSeek's
  // aligner weights) and a U8 tail, covering every byte after the header;
  // padded with spaces to a multiple of 8, as safetensors pads. The header's
  // length moves the data's size, so it is laid out until it stops moving.
  static char hdr[1 << 20];
  uint64_t tensor = 5120ull * 9216 * 2;
  int h = 0;
  for (uint64_t guess = 0, pass = 0; pass < 8; pass++) {
    uint64_t room = total > 8 + guess ? total - 8 - guess : 0, at = 0;
    h = snprintf(hdr, sizeof hdr, "{\"__metadata__\":{\"format\":\"pt\",\"synthetic\":\"blake3-bend\"}");
    for (uint64_t i = 0; at < room && h < (int)sizeof hdr - 256; i++) {
      uint64_t n = room - at < tensor ? room - at : tensor;
      int bf = n == tensor;
      h += snprintf(hdr + h, sizeof hdr - h,
                    ",\"layers.%llu.weight\":{\"dtype\":\"%s\",\"shape\":[%llu],\"data_offsets\":[%llu,%llu]}",
                    (unsigned long long)i, bf ? "BF16" : "U8", (unsigned long long)(bf ? n / 2 : n),
                    (unsigned long long)at, (unsigned long long)(at + n));
      at += n;
    }
    hdr[h++] = '}';
    while (h % 8) hdr[h++] = ' ';
    if ((uint64_t)h == guess) break;
    guess = (uint64_t)h;
  }
  data_at = 8 + (uint64_t)h;
  if (data_at > total) {
    fprintf(stderr, "synth: %llu bytes is too small\n", (unsigned long long)total);
    return 1;
  }
  fd = open(argv[1], O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) { perror(argv[1]); return 1; }
  uint64_t hl = (uint64_t)h;
  if (pwrite(fd, &hl, 8, 0) != 8 || pwrite(fd, hdr, (size_t)h, 8) != h) { perror("header"); return 1; }
  if (ftruncate(fd, (off_t)total) != 0) { perror("ftruncate"); return 1; }
  nblk = (total - data_at + BLK - 1) / BLK;
  struct timespec t0, t1;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  pthread_t t[256];
  if (threads < 1) threads = 1;
  if (threads > 256) threads = 256;
  for (int i = 0; i < threads; i++) pthread_create(&t[i], NULL, writer, NULL);
  for (int i = 0; i < threads; i++) pthread_join(t[i], NULL);
  if (fsync(fd) != 0) perror("fsync");
  close(fd);
  clock_gettime(CLOCK_MONOTONIC, &t1);
  double s = (double)(t1.tv_sec - t0.tv_sec) + (double)(t1.tv_nsec - t0.tv_nsec) * 1e-9;
  printf("wrote %s: %llu bytes in %.2f s (%.2f GB/s)\n", argv[1], (unsigned long long)total, s,
         (double)total / s / 1e9);
  return 0;
}
