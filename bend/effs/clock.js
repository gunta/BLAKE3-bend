function clock_us() {
  return Math.floor(performance.now() * 1000);
}

io_eff(CID(Clock.us), clock_us);
