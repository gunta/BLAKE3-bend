# turboblake brand

The landing page's identity, and why each piece is the way it is. Tokens live in
`src/styles/global.css` and `src/lib/brand.ts`; this file is the reasoning.

## Name

**turboblake**: the product, the crate and the command are one word.

```bash
brew install gunta/tap/turboblake
turboblake --check B3SUMS
```

- It belongs to the **turbo** family (like `turbotoken`): a drop-in replacement
  for a reference tool, made as fast as each machine allows.
- BLAKE3 is the subject; the engine is not in the name. Bend2 runs the tree on
  the CPU; native Metal and CUDA kernels take over the targets where they
  measure faster (ADR 0013), without a rename.
- Write it `turboblake`, always lowercase (it is a command). The wordmark sets
  "turbo" in volt and "blake" in ink.
- The repository stays `BLAKE3-bend`.

## Story, in the order a regular developer needs it

The home page is for people who hash files, not people who benchmark hashers.
Each section is one idea, shown before it is explained, laid out as bento tiles:

1. **What it does** (hero): checksum anything at the speed of your SSD; use it
   anywhere you use `sha256sum`.
2. **Speed** (bento): a handful of measured outcomes, big numbers, to scale.
   One footnote links the method; nothing about reproducing on the home page.
   Then **from SHA-256 to the GPU** (`Versus.astro`): one gigabyte on the
   fastest GPU measured and on the Mac, SHA-256, the official BLAKE3 and
   turboblake side by side, bars to scale, so the size of the jump is seen.
3. **What a checksum is:** a fingerprint for any data. Show it (the
   one-character demo) before explaining it.
4. **Why BLAKE3:** faster than SHA-256, safer than MD5, who already ships it,
   in the BLAKE3 team's own numbers and claims (`src/lib/official.ts`), linked.
5. **How it works:** split, spread, fold, on one diagram. Bend2 in one line.
6. **What's new:** the three newest changelog stories, the newest one large.
   The hero's "New" pill names the newest too.
7. **Install:** one line, over the aurora.

Everything else (every table, ties, floors, techniques, proofs, how to
reproduce) lives on `/benchmarks/`, with `/install/`, `/languages/` and `/gpu/`
beside it.

## The changelog (`/changelog/`)

Every ADR is told as news, newest first: a headline, a two-sentence standfirst
for someone who uses turboblake, one stat, and up to three points. Readers never
see ADR numbers or the words "decision record"; the full write-up is a link at
the foot of each story. That holds for every page, `summary` and `note` included:
`pnpm build` ends with `scripts/check-copy.ts`, which fails on either in the
built text. The words live beside the technical summary in
`results.json` `techniques` (`headline`, `dek`, `stat`, `points`, `tag`, `date`),
so the numbers keep one source. An ADR without them still appears, under its
own title. Headlines say what changed for the reader ("Files past 4 TiB"), not
what the code does ("the chunk counter's high word").

## Why Bend2 (the under-the-hood story)

BLAKE3 is a Merkle tree: 1 KiB chunks hashed independently, merged pairwise to
one root. Bend2 is a language whose programs fork into trees of independent
work that its runtime spreads over every CPU core or the GPU. A tree-shaped
hash, run by a tree-shaped language: that is the reason for the engine, and the
hero's light and the engine diagram both draw that tree.

## Voice

Calm, specific, honest. Sentence case. Numbers from `results.json`, never typed
into copy; claims about BLAKE3 itself are the BLAKE3 team's, linked; ties are
shown as plainly as wins. No racing metaphors.

## The mark: the Merge

BLAKE3's tree drawn sideways: four leaves merge in two levels into one root,
which lands on a dot, the digest. It also reads as a fast-forward arrow.

- The lines lean forward 10°; the dot stays round; strokes thicken toward the root.
- On dark: ion → volt gradient. App icon and favicon: the bold mark in near-black
  on a volt tile.
- Geometry: `MARK_PATHS` in `src/lib/brand.ts`. Never redraw it by hand.

## Color

| Token | Hex | Use |
| --- | --- | --- |
| void | `#060608` | page |
| surface / 2 / 3 | `#0c0c10` / `#131318` / `#1b1b22` | cards, code, controls |
| ink / 2 / 3 | `#ededef` / `#a9a9b4` / `#8a8a96` | text, by emphasis |
| **volt** | `#d4ff3a` | the brand word, results, focus; used sparingly |
| **ion** | `#46e3ff` | the GPU; the cold end of the tree's gradient |

Primary buttons are ink on void, not volt. Baselines in charts are gray and
always labelled.

## Type

**Geist** for everything, **Geist Mono** for commands, digests and labels.
Headlines weight 650 with tight tracking (−0.045em to −0.055em); no italics.

## Motion and shaders

Quick out, no bounce (`--ease-out`), 150 ms hovers, ~0.6 s reveals; everything
respects `prefers-reduced-motion`.

- **Hero, `merge.wgsl`** (vgpu on WebGPU): BLAKE3's tree in light, packets
  merging toward the root, a beam carrying the live digest's 256 bits. Typing in
  the demo sends a wave down the tree; the pointer bends the field. Kept calm:
  low bloom, no streaks. Static SVG from the same geometry without WebGPU.
- **Engine diagram:** eight chunks, three levels of parents, one root, with the
  levels lighting up in hashing order.

## Other projects' marks

Official marks name the projects the page talks about: BLAKE3, Bend, Rust, C,
iroh, DeepSeek, Hugging Face, NVIDIA, vgpu, WebGPU, Astro, GitHub. Sources are
in `src/lib/brands.ts`. They stay their owners' trademarks; mono by default.
Apple's logo is not used. UI icons are Lucide.

## Assets

- `/favicon.svg`, `/apple-touch-icon.png`: drawn from `iconSvg()` at build time.
- `/og.png`: built from the data, text outlined in Geist (`src/lib/outline.ts`).
