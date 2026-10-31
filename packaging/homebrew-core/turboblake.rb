class Turboblake < Formula
  desc "BLAKE3 checksums, turbocharged: a drop-in b3sum with a Bend2 engine"
  homepage "https://gunta.github.io/turboblake/"
  url "https://static.crates.io/crates/turboblake/turboblake-1.8.8.crate"
  sha256 "0dba52f897ec8d4b26977181a2cfc0810b269064f230f50edb00e603f84b326b"
  license any_of: [
    "CC0-1.0",
    "Apache-2.0",
    { "Apache-2.0" => { with: "LLVM-exception" } },
  ]

  depends_on "rust" => :build

  on_linux do
    depends_on "llvm" => :build
  end

  def install
    # The engine is C that clang vectorizes; without clang it builds as the official blake3.
    ENV["CC"] = formula_opt_bin("llvm")/"clang" if OS.linux?
    # The shims drop -O3, which the engine is tuned for, and -mcpu=native, which a bottle must not carry.
    ENV.O3
    ENV["TURBOBLAKE_PORTABLE"] = "1"
    # The command line stays on the CPU.
    ENV["TURBOBLAKE_NO_GPU"] = "1"
    system "cargo", "install", *std_cargo_args
  end

  test do
    (testpath/"hello.txt").write "hello, world"
    digest = "a1a55887535397bf461902491c8779188a5dd1f8c3951b3d9cf6ecba194e87b0"
    assert_equal "#{digest}  hello.txt", shell_output("#{bin}/turboblake hello.txt").strip
    (testpath/"B3SUMS").write "#{digest}  hello.txt\n"
    assert_equal "hello.txt: OK", shell_output("#{bin}/turboblake --check B3SUMS").strip
    assert_match version.to_s, shell_output("#{bin}/turboblake --version")
  end
end
