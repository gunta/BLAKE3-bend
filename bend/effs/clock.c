// Clock.us: microseconds on the runtime's monotonic tick.

Term clock_us_run(Env e, Term* f, IoWork* w) {
  return (Term)(io_tick() / 1000ull);
}

static void __attribute__((constructor)) clock_us_use(void) {
  io_eff(CID(Clock.us), clock_us_run);
}
