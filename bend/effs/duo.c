// Duo: two Bend processes hashing one input together (split.bend), one on
// the CPU pool and one on the GPU. They share a small block in a mapped file
// ($B3DUO, else /tmp/b3duo-<uid>): the leader (the CPU side) creates it and
// starts each round; the follower (the GPU side) says when it is ready for a
// round and posts its CVs when it is done. Effects only move words: every
// compression stays in Bend.

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>

#define DUO_MAGIC 0xB3D0B3D0u
#define DUO_WORDS 1024

typedef struct {
  u32 magic;
  u32 go;     // the round the leader has started
  u32 ready;  // the round the follower waits for
  u32 done;   // the round whose CVs are in w
  u32 n;      // CVs in w
  u32 pad[11];
  u32 w[DUO_WORDS];
} DuoBlk;

static DuoBlk* duo_blk;

static const char* duo_path(void) {
  static char buf[256];
  const char* p = getenv("B3DUO");
  if (p != NULL && *p != 0) {
    return p;
  }
  snprintf(buf, sizeof buf, "/tmp/b3duo-%u", (unsigned)getuid());
  return buf;
}

static void duo_die(const char* what) {
  fprintf(stderr, "duo: %s (%s)\n", what, duo_path());
  exit(2);
}

// Spins until *p has reached round r (wrapping compare); a minute at most.
static u32 duo_spin(u32* p, u32 r) {
  u64 t0 = io_tick();
  for (u64 i = 0;; i += 1) {
    u32 v = __atomic_load_n(p, __ATOMIC_ACQUIRE);
    if ((int32_t)(v - r) >= 0) {
      return v;
    }
    if ((i & 0xFFFF) == 0 && io_tick() - t0 > 60000000000ull) {
      duo_die("the other side never came");
    }
  }
}

// Duo.open(lead): the leader creates and clears the block; the follower
// waits for it to appear.
Term duo_open_run(Env e, Term* f, IoWork* w) {
  bool lead = (u32)f[0] != 0;
  const char* path = duo_path();
  int fd = -1;
  if (lead) {
    unlink(path);
    fd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0600);
    if (fd < 0 || ftruncate(fd, sizeof(DuoBlk)) != 0) {
      duo_die("cannot create the block");
    }
  } else {
    u64 t0 = io_tick();
    struct stat st;
    while ((fd = open(path, O_RDWR)) < 0 || fstat(fd, &st) != 0 ||
      st.st_size < (off_t)sizeof(DuoBlk)) {
      if (fd >= 0) {
        close(fd);
      }
      if (io_tick() - t0 > 60000000000ull) {
        duo_die("no leader");
      }
      usleep(1000);
    }
  }
  duo_blk = mmap(NULL, sizeof(DuoBlk), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  close(fd);
  if (duo_blk == MAP_FAILED) {
    duo_die("cannot map the block");
  }
  if (lead) {
    memset(duo_blk, 0, sizeof(DuoBlk));
    __atomic_store_n(&duo_blk->magic, DUO_MAGIC, __ATOMIC_RELEASE);
  } else {
    duo_spin(&duo_blk->magic, DUO_MAGIC);
  }
  return (Term)0;
}

// Duo.ready(r), leader: waits until the follower waits for round r.
Term duo_ready_run(Env e, Term* f, IoWork* w) {
  return (Term)duo_spin(&duo_blk->ready, (u32)f[0]);
}

// Duo.go(r), leader: starts round r.
Term duo_go_run(Env e, Term* f, IoWork* w) {
  __atomic_store_n(&duo_blk->go, (u32)f[0], __ATOMIC_RELEASE);
  return (Term)0;
}

// Duo.wait(r), follower: says it is ready for round r, waits for its start.
Term duo_wait_run(Env e, Term* f, IoWork* w) {
  u32 r = (u32)f[0];
  __atomic_store_n(&duo_blk->ready, r, __ATOMIC_RELEASE);
  return (Term)duo_spin(&duo_blk->go, r);
}

// Duo.put(i, w0..w7), follower: CV i of this round.
Term duo_put_run(Env e, Term* f, IoWork* w) {
  u32 i = (u32)f[0];
  if (i >= DUO_WORDS / 8) {
    duo_die("too many CVs");
  }
  for (u32 k = 0; k < 8; k += 1) {
    duo_blk->w[i * 8 + k] = (u32)f[1 + k];
  }
  return (Term)0;
}

// Duo.done(r, n), follower: round r's n CVs are posted.
Term duo_done_run(Env e, Term* f, IoWork* w) {
  duo_blk->n = (u32)f[1];
  __atomic_store_n(&duo_blk->done, (u32)f[0], __ATOMIC_RELEASE);
  return (Term)0;
}

// Duo.await(r, x), leader: waits for round r's CVs, answers how many. x is
// any word of the leader's own share, so its hashing comes first.
Term duo_await_run(Env e, Term* f, IoWork* w) {
  duo_spin(&duo_blk->done, (u32)f[0]);
  return (Term)duo_blk->n;
}

// Duo.get(i), leader: word i of the posted CVs.
Term duo_get_run(Env e, Term* f, IoWork* w) {
  return (Term)duo_blk->w[(u32)f[0] % DUO_WORDS];
}

static void __attribute__((constructor)) duo_use(void) {
  io_eff(CID(Duo.open), duo_open_run);
  io_eff(CID(Duo.ready), duo_ready_run);
  io_eff(CID(Duo.go), duo_go_run);
  io_eff(CID(Duo.wait), duo_wait_run);
  io_eff(CID(Duo.put), duo_put_run);
  io_eff(CID(Duo.done), duo_done_run);
  io_eff(CID(Duo.await), duo_await_run);
  io_eff(CID(Duo.get), duo_get_run);
}
