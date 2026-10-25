# B3ND brand

The landing page's identity, and why each piece is the way it is. Tokens live in
`src/styles/global.css` and `src/lib/brand.ts`; this file is the reasoning.

## Name

**B3ND**, said "bend". It is Bend, spelled with BLAKE3's 3: the same "b3" as
`b3sum`. One four-letter word puts the language first and still names the hash.
The descriptor always travels with it on first mention: **BLAKE3 in Bend2**.

- Write it `B3ND`, all caps, the 3 a digit. In running text, introduce it once
  as "B3ND (say “bend”)".
- In the wordmark only the 3 is volt; the rest is ink.
- The repository (`BLAKE3-bend`) and the crate (`b3sum-bend`) keep their names.

## Voice

Fast and honest. The page says where B3ND wins, where it only ties, and which
floors stop both sides; the brand never rounds a tie up to a win. Racing
language is seasoning, not the meal: laps for sections, a finish line at the
end, numbers first.

- Tagline: **Bend the tree. Beat the clock.**
- Lead with measured numbers, from `results.json`, never typed into copy.

## The mark: the Merge

BLAKE3's tree, drawn sideways. Four leaves, speed lines of uneven length,
merge in two levels into one root, and the root lands on a dot: the digest.
It also reads as a fast-forward arrow and as Bend's `fork`, run backwards.

- The lines lean forward 10°; the dot stays round.
- Strokes thicken toward the root (3.6 → 4.6 → 5.6 units), the way work piles up
  as the tree merges.
- On dark: ion → volt gradient, or solid volt. App icon and favicon: the bold
  mark in near-black on a volt tile, like a race number plate.
- Geometry: `MARK_PATHS` in `src/lib/brand.ts`. Never redraw it by hand.

## Color: Night Race

| Token | Hex | Use |
| --- | --- | --- |
| void | `#060608` | page |
| surface / 2 / 3 | `#0c0c11` / `#14141b` / `#1d1d27` | cards, code, controls |
| ink / 2 / 3 | `#f4f3ee` / `#b8b7c4` / `#8f8e9e` | text, by emphasis |
| **volt** | `#d4ff3a` | the brand; Bend CPU series; links |
| **ion** | `#46e3ff` | the GPU; the cold end of the heat gradient |
| plasma | `#ff4f8b` | a second Bend series; caveats |

Data "heats up" from ion to volt, as it does in the hero, where leaves start
cyan and the root burns lime. Baselines are always gray and always labelled:
color never carries a result alone.

## Type

- **Archivo** (variable, width 62–125): display at 125% width, weight ~820,
  uppercase, tight tracking; italic for anything that should feel like motion.
  Body at 100% width.
- **Martian Mono**: kickers, labels, digests, commands.
- The second headline line gets a motion smear (stacked offset text-shadows).

## Motion

Quick out, no bounce: `--ease-out` (0.16, 1, 0.3, 1), 160 ms for hovers, ~0.7 s
for reveals. Everything respects `prefers-reduced-motion`: shaders draw one still
frame, the race shows its finish, the ticker becomes a scroller.

## Shaders (vgpu on WebGPU)

- **Hero, `merge.wgsl`**: the Merge at full size: 32 leaves, packets racing to
  the root, a flare, and a beam that carries the live digest's 256 bits. Typing
  in the hash box sends a wave down the tree; the pointer bends the field (the
  name, made literal); a click floors it. HDR, two-band bloom, ACES, grain.
- **Footer, `flag.wgsl`**: a charcoal checkered flag with a volt light sweep;
  the pointer pushes ripples through it.
- Without WebGPU the same tree is static SVG (`src/lib/tree.ts`) and the flag is
  CSS; canvases only draw while on screen.

## Other projects' marks

Official marks name the projects the page talks about: BLAKE3 (upstream
`media/`), Bend, Rust, C, iroh, DeepSeek, Hugging Face, NVIDIA, vgpu, WebGPU,
Astro, GitHub. Sources are listed in `src/lib/brands.ts`. They stay their
owners' trademarks and are shown in their own shapes, mono by default and in
their own colors on hover. Apple's logo is not used; the machine gets a chip icon.
UI icons are Lucide.

## Assets

- `/favicon.svg`, `/apple-touch-icon.png`: drawn from `iconSvg()` at build time.
- `/og.png`: the card, built from the headlines with text outlined in the brand
  fonts (`src/lib/outline.ts`), so previews never show stale numbers.
