/**
 * One guide per language, each its own page (/install/<slug>/) with its own SKILL.md
 * (src/skills/<slug>.md, served at /install/<slug>/SKILL.md): the install line for every
 * package manager of that language, the code swap, what to know, and the card on the home
 * page and /install/ (LanguageInstalls.astro). The version in skills comes from the crate.
 */
import type { MarkName } from './brands';
import { CLI_VERSION } from './site';
import rustSkill from '../skills/rust.md?raw';
import pythonSkill from '../skills/python.md?raw';
import typescriptSkill from '../skills/typescript.md?raw';
import goSkill from '../skills/go.md?raw';
import cSkill from '../skills/c.md?raw';

/** One block of code, highlighted as `lang`. */
export interface Snippet {
  /** The tab's or the block's label. */
  label: string;
  lang: string;
  code: string;
  mark?: MarkName;
}

export interface Guide {
  slug: string;
  title: string;
  mark: MarkName;
  /** The card's accent: the language's own color, lightened where its mark is dark. */
  accent: string;
  /** The page's <title> and its description, for search. */
  seoTitle: string;
  description: string;
  /** What the package is called on its registry. */
  name: string;
  registry: { name: string; mark?: MarkName; url: string };
  /** The card's one line, and the tools it also shows. */
  command: string;
  also?: string[];
  /** The BLAKE3 packages it stands in for: the card's short line, and the page's list. */
  replacesShort: string;
  replaces: string[];
  lede: string;
  /** Install: one tab per package manager (a tab group shared by every page of the language). */
  install: Snippet[];
  /** Use: blocks in order; each is a single block or a set of tabs. */
  use: { title: string; text?: string; tabs: Snippet[] }[];
  notes: string[];
  readme: string;
  skill: string;
}

const skill = (s: string) => s.replaceAll('{{version}}', CLI_VERSION);

export const GUIDES: readonly Guide[] = [
  {
    slug: 'rust',
    title: 'Rust',
    mark: 'rust',
    accent: '#f46623',
    seoTitle: 'BLAKE3 for Rust on every core: a drop-in for the blake3 crate',
    description:
      'turboblake is the blake3 crate with big inputs hashed on every CPU core and the GPU. Same API, same use blake3::…, same output. Install with cargo add turboblake, or patch it under a whole dependency graph.',
    name: 'turboblake',
    registry: { name: 'crates.io', url: 'https://crates.io/crates/turboblake' },
    command: 'cargo add turboblake',
    replacesShort: 'blake3',
    replaces: ['blake3'],
    lede: 'The official blake3 crate with one change: once an update is big enough, it is hashed on every core. The library is still named blake3, so your code compiles unchanged.',
    install: [
      { label: 'cargo', lang: 'bash', code: 'cargo add turboblake' },
      { label: 'Cargo.toml', lang: 'toml', code: '[dependencies]\n# the library only, without the command line\nturboblake = { version = "1.8", default-features = false, features = ["std"] }' },
      {
        label: 'Keep the name',
        lang: 'toml',
        code: '[dependencies]\n# was: blake3 = { version = "1.8", features = ["rayon"] }\nblake3 = { package = "turboblake", version = "1.8", default-features = false, features = ["std", "rayon"] }',
      },
      {
        label: 'Every crate in the graph',
        lang: 'bash',
        code: `git clone --depth 1 --branch turboblake-v${CLI_VERSION} https://github.com/gunta/turboblake /tmp/turboblake\nTURBOBLAKE_NAME=blake3 /tmp/turboblake/bend/rust/gen.sh vendor/blake3\n\n# then, in the workspace's Cargo.toml:\n#   [patch.crates-io]\n#   blake3 = { path = "vendor/blake3" }`,
      },
    ],
    use: [
      {
        title: 'Your code, unchanged',
        tabs: [
          {
            label: 'main.rs',
            lang: 'rust',
            code: 'let hash = blake3::hash(b"hello world");\n\nlet mut hasher = blake3::Hasher::new_keyed(&key);\nhasher.update(&big_buffer);           // every core, past ~256 KiB\nhasher.update_mmap_rayon("big.iso")?; // features "mmap" and "rayon"\nlet out = hasher.finalize_xof();      // extended output, as upstream',
          },
        ],
      },
      {
        title: 'GPU memory, where it is',
        text: 'Loaded at run time: Metal on macOS, CUDA through libcuda elsewhere. Without a GPU nothing changes.',
        tabs: [
          {
            label: 'gpu.rs',
            lang: 'rust',
            code: 'let mut h = blake3::Hasher::new();\nunsafe { h.update_cuda(tensor_ptr, len, std::ptr::null_mut()) }; // CUDA device memory\nunsafe { h.update_metal(mtl_buffer, offset, len) };               // an id<MTLBuffer>\nlet m = blake3::gpu::Memory::new(1 << 30).unwrap();                // host memory the GPU reads\nblake3::hash(&m);                                                  // split between CPU and GPU\nblake3::gpu::backend();                                            // which one runs',
          },
        ],
      },
    ],
    notes: [
      'hash, Hasher::update, keyed_hash, derive_key and extended output reach the engine past a size it calibrates at the first big input (about 256 KiB on an Apple M5 Pro). update_rayon hands it the part it beats rayon on. Below that, and in no_std builds, it is upstream’s code.',
      'Building needs clang. Without it, and on Windows, the crate builds as upstream’s and says so in a warning: the same results at upstream’s speed.',
      'The crate also holds the turboblake command, behind its default cli feature: default-features = false, features = ["std"] leaves its dependencies out.',
    ],
    readme: 'bend/rust/README.md',
    skill: skill(rustSkill),
  },
  {
    slug: 'python',
    title: 'Python',
    mark: 'python',
    accent: '#5a9fd4',
    seoTitle: 'BLAKE3 for Python on every core: a drop-in for the blake3 package',
    description:
      'turboblake installs the same blake3 module as the blake3 package on PyPI, with big inputs hashed on every CPU core and the GPU. Prebuilt wheels for macOS and Linux; pip, uv, Poetry and PDM.',
    name: 'turboblake',
    registry: { name: 'PyPI', mark: 'pypi', url: 'https://pypi.org/project/turboblake/' },
    command: 'pip install turboblake',
    also: ['uv add turboblake'],
    replacesShort: 'blake3',
    replaces: ['blake3 (PyPI)'],
    lede: 'The same blake3 module as blake3 on PyPI, whose test suite it passes, with big inputs hashed on every core. Remove blake3, add turboblake; your imports stay.',
    install: [
      { label: 'pip', lang: 'bash', code: 'pip uninstall -y blake3\npip install turboblake' },
      { label: 'uv', lang: 'bash', code: 'uv remove blake3   # if the project had it\nuv add turboblake' },
      { label: 'Poetry', lang: 'bash', code: 'poetry remove blake3\npoetry add turboblake' },
      { label: 'PDM', lang: 'bash', code: 'pdm remove blake3\npdm add turboblake' },
      { label: 'requirements.txt', lang: 'text', code: '# was: blake3>=1.0\nturboblake>=1.8' },
    ],
    use: [
      {
        title: 'Your code, unchanged',
        tabs: [
          {
            label: 'app.py',
            lang: 'python',
            code: 'from blake3 import blake3\n\nblake3(b"hello world").hexdigest()\nblake3(data, key=key).digest(length=64, seek=0)\nhasher = blake3(derive_key_context="example.com 2026-10-26 session keys")\nhasher.update_mmap("big.iso")   # every core, mapped from disk',
          },
        ],
      },
      {
        title: 'Tensors on the GPU',
        text: 'CUDA device memory and Metal buffers are hashed where they are, without a copy to the host.',
        tabs: [
          {
            label: 'gpu.py',
            lang: 'python',
            code: 'import blake3, torch\n\nt = torch.load("weights.pt", map_location="cuda")\nh = blake3.blake3()\nh.update_cuda(t.data_ptr(), t.numel() * t.element_size())  # stream=0\nh.hexdigest()\nblake3.gpu()   # "cuda", "metal" or None',
          },
        ],
      },
    ],
    notes: [
      'Both packages provide the module blake3, so install one: remove blake3, add turboblake. If another package requires blake3, its resolver installs it again beside turboblake.',
      'Wheels with the engine for macOS and Linux (glibc 2.28+ and musl), arm64 and x86-64, every CPython from 3.9. On Windows, where the engine does not run yet, turboblake installs the official blake3: never slower than upstream.',
      'max_threads is accepted and ignored: big updates already use every core.',
    ],
    readme: 'bend/python/README.md',
    skill: skill(pythonSkill),
  },
  {
    slug: 'typescript',
    title: 'TypeScript',
    mark: 'typescript',
    accent: '#4a9be8',
    seoTitle: 'BLAKE3 for TypeScript and JavaScript: native on every core, in Node, Bun, Deno and browsers',
    description:
      'turboblake is BLAKE3 for TypeScript and JavaScript: a prebuilt native addon that hashes big inputs on every core in Node.js, Bun and Deno, and pure JavaScript in browsers. A drop-in for @noble/hashes/blake3 and the blake3 package, with types.',
    name: 'turboblake',
    registry: { name: 'npm', mark: 'npm', url: 'https://www.npmjs.com/package/turboblake' },
    command: 'npm install turboblake',
    also: ['bun add turboblake', 'deno add npm:turboblake'],
    replacesShort: '@noble/hashes, blake3',
    replaces: ['@noble/hashes/blake3', 'blake3 (npm)', 'hash-wasm', '@napi-rs/blake-hash'],
    lede: 'One package, typed, with both APIs JavaScript uses for BLAKE3. Native on every core in Node.js, Bun and Deno; pure JavaScript in browsers and workers. Nothing compiles on install.',
    install: [
      { label: 'npm', mark: 'npm', lang: 'bash', code: 'npm install turboblake' },
      { label: 'pnpm', lang: 'bash', code: 'pnpm add turboblake' },
      { label: 'yarn', lang: 'bash', code: 'yarn add turboblake' },
      { label: 'bun', mark: 'bun', lang: 'bash', code: 'bun add turboblake' },
      { label: 'deno', mark: 'deno', lang: 'bash', code: 'deno add npm:turboblake' },
    ],
    use: [
      {
        title: 'Swap the import',
        text: 'Pick the API your code already uses; the rest stays.',
        tabs: [
          {
            label: '@noble/hashes',
            lang: 'ts',
            code: '// was: import { blake3 } from "@noble/hashes/blake3.js";\nimport { blake3 } from "turboblake";\n\nblake3(data);                                // Uint8Array(32)\nblake3(data, { dkLen: 64, key });            // keyed, extended output\nblake3.create({ context }).update(a).update(b).digest();',
          },
          {
            label: 'blake3 (npm)',
            lang: 'ts',
            code: '// was: import { hash, createHash } from "blake3";\nimport { hash, keyedHash, deriveKey, createHash } from "turboblake";\n\nhash("hello").toString("hex");\ncreateHash().update(buf).digest("hex", { length: 64 });',
          },
          {
            label: 'hash-wasm',
            lang: 'ts',
            code: '// was: const hex = await blake3(data);       (hash-wasm: async, hex)\nimport { blake3 } from "turboblake";\n\nconst hex = Buffer.from(blake3(data)).toString("hex"); // synchronous\nconst wide = blake3(data, { dkLen: 64 });            // was: blake3(data, 512)',
          },
        ],
      },
      {
        title: 'Many files, and which engine runs',
        tabs: [
          {
            label: 'files.ts',
            lang: 'ts',
            code: 'import { hashFiles, backend } from "turboblake";\n\nconst sums = await hashFiles(["a.iso", "b.iso"]); // Uint8Array, or an Error with errno\nconsole.log(backend); // "native" in Node, Bun and Deno; "bend-js" in browsers',
          },
          {
            label: 'browser.ts',
            lang: 'ts',
            code: '// Bundlers pick the JavaScript build for browsers and workers on their own.\nimport { blake3 } from "turboblake";\n// or ask for it anywhere:\nimport { blake3 as blake3js } from "turboblake/js";',
          },
        ],
      },
    ],
    notes: [
      'The native addon comes prebuilt inside the package for macOS, Linux (glibc and musl) and Windows, arm64 and x64, and loads the one for your machine: no install script. On Windows it is the official C (no engine there yet). Anywhere else turboblake runs on Bend’s JavaScript.',
      'The package is ESM with its own types. CommonJS can require() it on Node 20.19+ and 22.12+.',
      'When bundling for Node, mark turboblake as external so the addon loads at run time.',
    ],
    readme: 'bend/node/README.md',
    skill: skill(typescriptSkill),
  },
  {
    slug: 'go',
    title: 'Go',
    mark: 'go',
    accent: '#00add8',
    seoTitle: 'BLAKE3 for Go on every core: a drop-in for lukechampine.com/blake3 and zeebo/blake3',
    description:
      'turboblake for Go: drop-in packages for lukechampine.com/blake3 and github.com/zeebo/blake3 that hash big inputs on every CPU core through cgo, with the same functions, types and output.',
    name: 'github.com/gunta/turboblake/bend/go',
    registry: { name: 'Go modules', url: 'https://pkg.go.dev/github.com/gunta/turboblake/bend/go' },
    command: 'go get github.com/gunta/turboblake/bend/go',
    replacesShort: 'lukechampine.com/blake3, zeebo/blake3',
    replaces: ['lukechampine.com/blake3', 'github.com/zeebo/blake3'],
    lede: 'Two drop-in packages, one for each BLAKE3 module Go code uses, with the same functions, types and output. Keep the package name blake3 and only the import line changes.',
    install: [{ label: 'go', lang: 'bash', code: 'go get github.com/gunta/turboblake/bend/go' }],
    use: [
      {
        title: 'Swap the import',
        tabs: [
          {
            label: 'lukechampine.com/blake3',
            lang: 'go',
            code: '// was: import "lukechampine.com/blake3"\nimport blake3 "github.com/gunta/turboblake/bend/go"\n\nsum := blake3.Sum256(data)\nh := blake3.New(64, key)              // hash.Hash; h.XOF() for extended output\nsums, errs := blake3.HashFiles(paths) // many files at once',
          },
          {
            label: 'github.com/zeebo/blake3',
            lang: 'go',
            code: '// was: import "github.com/zeebo/blake3"\nimport blake3 "github.com/gunta/turboblake/bend/go/zeebo"\n\nh := blake3.New()\nh.Write(data)\nsum := h.Sum(nil)',
          },
        ],
      },
    ],
    notes: [
      'Needs cgo. The engine is linked prebuilt for darwin and linux on arm64 and amd64; other Unix systems compile it through cgo at plain flags, slower and still on every core. On Windows (MinGW) the package is the official C alone.',
      'Additions: NewDeriveKey, Hasher.Clone and HashFiles. One deliberate difference: after OutputReader.Seek to an offset that is not a multiple of 1024, lukechampine.com/blake3 v1.4.1 returns wrong bytes; this package returns BLAKE3’s.',
    ],
    readme: 'bend/go/README.md',
    skill: skill(goSkill),
  },
  {
    slug: 'c',
    title: 'C',
    mark: 'c',
    accent: '#a8b9cc',
    seoTitle: 'BLAKE3 for C and C++ on every core: libturboblake, a drop-in for blake3.h',
    description:
      'libturboblake is the official BLAKE3 C library, blake3.h unchanged, with big inputs hashed on every CPU core and the GPU. Relink and run: Homebrew, CMake, pkg-config or the release archives.',
    name: 'libturboblake',
    registry: { name: 'Homebrew', mark: 'homebrew', url: 'https://github.com/gunta/homebrew-tap' },
    command: 'brew install gunta/tap/libturboblake',
    also: ['cmake -S bend/lib'],
    replacesShort: 'blake3.h',
    replaces: ['the official C library (blake3.h, libblake3)'],
    lede: 'The official BLAKE3 C library, blake3.h unchanged: same symbols, same blake3_hasher layout. Programs keep #include "blake3.h" and relink.',
    install: [
      { label: 'Homebrew', mark: 'homebrew', lang: 'bash', code: 'brew install gunta/tap/libturboblake' },
      {
        label: 'CMake',
        mark: 'cmake',
        lang: 'bash',
        code: `git clone --depth 1 --branch turboblake-v${CLI_VERSION} https://github.com/gunta/turboblake\ncmake -S turboblake/bend/lib -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang\ncmake --build build && cmake --install build --prefix /usr/local`,
      },
      {
        label: 'Release archive',
        lang: 'bash',
        code: `# macOS and Linux, arm64 and x86-64: static and shared, pkg-config, CMake package\ncurl -LO https://github.com/gunta/turboblake/releases/download/turboblake-v${CLI_VERSION}/libturboblake-${CLI_VERSION}-aarch64-apple-darwin.tar.gz`,
      },
    ],
    use: [
      {
        title: 'Link it',
        text: 'Headers install under include/turboblake/, beside any official blake3.h, never over it.',
        tabs: [
          { label: 'CMake', mark: 'cmake', lang: 'cmake', code: 'find_package(turboblake REQUIRED)\ntarget_link_libraries(app PRIVATE turboblake::turboblake)' },
          { label: 'pkg-config', lang: 'bash', code: 'cc app.c $(pkg-config --cflags --libs libturboblake) -o app' },
          { label: 'Makefile', lang: 'makefile', code: 'CFLAGS += -I$(PREFIX)/include/turboblake\nLDLIBS += -lturboblake -lpthread -lm' },
        ],
      },
      {
        title: 'Your code, unchanged',
        tabs: [
          {
            label: 'app.c',
            lang: 'c',
            code: '#include "blake3.h"\n\nblake3_hasher h;\nblake3_hasher_init(&h);\nblake3_hasher_update(&h, buf, len);   // every core, past ~256 KiB\nuint8_t out[BLAKE3_OUT_LEN];\nblake3_hasher_finalize(&h, out, BLAKE3_OUT_LEN);',
          },
        ],
      },
    ],
    notes: [
      'The engine needs clang on a POSIX system; elsewhere (Windows, gcc) CMake builds the official C alone. -DTURBOBLAKE_TARGET_CPU=native tunes it for the build machine.',
      'turboblake.h adds the GPU calls: turboblake_hasher_update_metal and turboblake_hasher_update_cuda hash GPU memory where it is, and turboblake_alloc gives host memory the GPU reads.',
    ],
    readme: 'bend/lib/README.md',
    skill: skill(cSkill),
  },
];

export function guide(slug: string): Guide {
  const g = GUIDES.find((x) => x.slug === slug);
  if (!g) throw new Error(`no guide ${slug}`);
  return g;
}
