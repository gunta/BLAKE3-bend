# b3bend brand

The landing page's identity, and why each piece is the way it is. Tokens live in
`src/styles/global.css` and `src/lib/brand.ts`; this file is the reasoning.

## Name

**b3bend**: the name, the crate and the command are one word.

```bash
cargo install b3bend
b3bend FILE...
```

- **BLAKE3 first.** `b3` is BLAKE3's own shorthand, as in the official `b3sum`;
  "bend" comes second, as the way it got faster. The subject is BLAKE3, the hash
  that replaces SHA-256, not the language.
- **Easy to type.** Six lowercase keys: no shift, no dot, no hyphen. It prints
  the same lines as `b3sum`.
- **Write it** `b3bend`, always lowercase (it is a command). The wordmark sets
  "b3" in ink and "bend" in volt.
- Passed over: BLAKE3b (BLAKE2b and BLAKE2s are variants with different
  digests, and these digests are byte-identical to BLAKE3's), blake3.bend (a dot
  cannot be a crate name), B3ND (reads as if Bend were the product).
- The repository stays `BLAKE3-bend`; the crate was renamed from `b3sum-bend`
  before its first release.

## Promise and voice

**The SHA-256 replacement, bent for speed.** The SHA-256 half is BLAKE3's own
claim (much faster than SHA-2, and safe from length extension, unlike SHA-2;
see the upstream README) and the page links to it rather than measuring it. The
speed half is what this page measures: b3bend against the official BLAKE3.

Fast and honest. The page says where it wins, where it only ties, and which
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
