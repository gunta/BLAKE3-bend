# Background images

Every background on the home page is a photograph in a named slot
(`src/components/Backdrop.astro`). To fill a slot, save the image as
`src/assets/bg/<slot>.png` (or `.jpg`/`.webp`) and rebuild: Astro serves it as AVIF and
WebP at 960 to 3200 px wide, quality 90. An empty slot renders nothing, so the page
works with any subset of the images.

| Slot | Where | Ratio | Text sits | Scrim |
| --- | --- | --- | --- | --- |
| `hero` | first screen, full bleed | 16:9 | left 45% | left |
| `speed` | "Hours become seconds." | 16:9 | everywhere (tiles) | edges |
| `tile-model` | "A model bigger than RAM" tile | 3:2 | top-left | bottom |
| `versus` | "N× faster than SHA-256." | 16:9 | everywhere (charts) | edges |
| `things` | the scrolling file-type band | 21:9 | center band | center |
| `checksum` | "A fingerprint for any file." | 16:9 | left half | edges |
| `tile-fingerprint` | the "edit either line" demo tile | 4:3 | everywhere | bottom |
| `why` | "The modern fingerprint." | 16:9 | everywhere (tiles) | edges |
| `tile-fast` | "N× faster than SHA-256, on a single core" tile | 4:3 | top-left | bottom |
| `how` | "BLAKE3 is a tree. Bend2 runs trees." | 16:9 | everywhere (diagram) | edges |
| `news` | "Faster with every update." | 16:9 | everywhere (tiles) | edges |
| `tile-news` | the newest-story tile | 16:10 | left and bottom | bottom |
| `install` | "Ready in one line." | 16:9 | center | center |

Generate the largest landscape size the model offers. If it tops out below 3200 px
wide, upscale 2× with a photographic upscaler before saving; never ship a soft image
for the hero.

## How these prompts are written

- **One art direction for all thirteen**, repeated inside every prompt (each
  generation starts fresh, so nothing carries over): low-key studio or night
  photography, near-black ground, two accent lights in the brand colors.
- **Scene, subject, composition, light, lens, palette, finish, exclusions**, in that
  order, as plain sentences. Concrete physical objects, real materials, real camera
  settings: the model renders what is described, so nothing is left as an abstraction
  like "speed" or "security".
- **Hex colors named once with their role.** Volt `#d4ff3a` is the hot, rare accent
  (the root, the result); ion `#46e3ff` is the cold, wider light; everything else falls
  to `#060608`.
- **Negative space stated as a fraction of the frame**, because copy and charts sit
  on top and the scrim alone cannot rescue a busy image.
- **The brand's own limits as exclusions**: calm, specific, honest, no racing
  metaphors. So no cars, speedometers, motion-blur streaks, flames, rockets, or
  "hacker" clichés (green code rain, padlocks, glowing circuit brains, binary digits).
- **No text, logos, or watermarks**, ever: every word on the page is live HTML.
- The recurring motif is **BLAKE3's tree**: many fine things merging, level by level,
  into one bright point. Show it in real matter (glass fiber, lightning, leaf veins,
  rivers), never as a diagram.

If a result comes back too bright or too busy, reply in the same chat with an edit
instead of starting over: "Keep everything, but darken the left half to pure black and
remove the highlights there", or "Same image, 30% less detail, more falloff to black".

---

## `hero`

```text
A photorealistic, ultra-high-resolution studio macro photograph for the hero background of a premium developer-tool website. Wide 16:9 landscape.

Subject: hundreds of hair-thin optical glass fibers emerge from deep darkness on the left-center of the frame and merge, level by level, like a binary tree turned on its side: pairs of fibers fuse into a strand, pairs of strands into a thicker bundle, four or five levels, until a single bright bundle meets one round glowing point at about 75% of the frame width and vertical center. The branches lean slightly forward, about 10 degrees, toward the right. The fibers get visibly thicker toward the root.

Light: the fibers carry light inside them. The thin outer fibers glow a cool cyan (#46e3ff), shifting smoothly through the merges to a vivid electric yellow-green (#d4ff3a) at the root. The root point is a small, intense, almost white core with a soft yellow-green bloom, like a single LED seen through glass. A faint thin line of yellow-green light continues from the root to the right edge of the frame. No other light source; light only leaks from the fiber ends and edges, with tiny specular glints along the glass.

Composition: the left 45% of the frame is near-black and empty (headline text goes there), with only the faintest out-of-focus fiber tips at the far left. Generous black space above and below the tree. The root sits on the right third line.

Camera: 100mm macro lens, f/5.6, focus stacked so the merge region is tack sharp and the farthest fibers fall into soft bokeh. Shot on a medium-format digital back, 16-bit, clean shadows, no noise.

Palette and finish: near-black background (#060608), not gray; deep crushed blacks; only cyan and yellow-green light. Calm, precise, expensive, quiet. Subtle natural film-like grain at the finest level only.

Avoid: text, letters, numbers, logos, watermarks, UI, circuit-board clichés, binary digits, padlocks, motion-blur streaks, speed lines, cars, flames, lens flare stars, rainbow dispersion, purple or magenta, haze or fog filling the frame.
```

## `speed`

```text
A photorealistic, low-key macro photograph used as a subtle full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: an extreme close-up of the surface of a bare silicon chip die: the fine metal interconnect layers and repeating rectangular blocks of a modern processor, many identical cores laid out in a precise grid, seen at a low raking angle so the grid recedes into the distance.

Light: a single narrow raking light from the upper left, colored cool cyan (#46e3ff), catches only the top edges of the metal traces, so the structure reads as fine glowing lines. One small area near the top left picks up a faint electric yellow-green (#d4ff3a) reflection. Everything else falls off quickly into black.

Composition: very low detail density; most of the frame (at least 70%) is near-black (#060608). The lit area is a soft diagonal band across the upper-left third. Strong depth of field falloff: sharp in a narrow band, soft bokeh before and after. No single focal object; it must sit quietly behind cards of text and numbers.

Camera: 100mm macro, f/4, tilt lens for a thin diagonal plane of focus. Medium-format, 16-bit, clean shadows.

Finish: crushed blacks, restrained, calm, precise, premium. No vignette halo, no glow haze.

Avoid: text, logos, chip brand markings, numbers, watermarks, rainbow diffraction colors, purple, motion blur, speed lines, flames, fantasy circuit art.
```

## `tile-model`

```text
A photorealistic product macro photograph for a small card background on a website. 3:2 landscape.

Subject: the top of a modern data-center accelerator board in near darkness: a large square processor package surrounded by tall stacks of high-bandwidth memory chips, the stacks seen at an angle so their layered edges are visible, like tiny skyscrapers of silicon. Scale should feel enormous: memory as architecture.

Light: one soft cyan (#46e3ff) rim light from behind, outlining the stack edges; a small electric yellow-green (#d4ff3a) specular highlight on the top right corner of the main package. The rest of the board falls into black.

Composition: subject occupies the upper right; the left and top-left 40% stays near-black (#060608) for a headline and a progress bar. Shallow depth of field, focus on the nearest memory stack.

Camera: 90mm macro, f/2.8, medium-format, 16-bit, clean.

Finish: deep blacks, premium product photography, calm.

Avoid: text, logos, brand names, labels, numbers, watermarks, fans, RGB lighting, purple, smoke, motion blur.
```

## `versus`

```text
A photorealistic aerial photograph at night for a subtle full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: a braided river delta seen straight down from high altitude: dozens of thin water channels on the right side of the frame merge step by step into fewer, wider channels and finally into one broad river flowing out toward the left. The tree of channels reads clearly from above.

Light: blue hour just after full darkness. The water carries a faint cool cyan (#46e3ff) reflection of the sky; the single main river carries a faint yellow-green (#d4ff3a) sheen where it is widest. The land between the channels is near-black, almost featureless, with a fine natural texture of sand and silt.

Composition: very calm, low contrast, low detail; at least 65% of the frame is near-black (#060608). The channel network occupies the right two thirds and stays dim; charts and text will sit on top of the whole frame.

Camera: satellite-style orthographic top-down view, long lens, tack sharp, no perspective tilt. 16-bit, clean shadows, no noise.

Finish: restrained, cinematic, monochrome except for the two accent tints.

Avoid: text, labels, map markings, roads, city lights, boats, clouds, watermarks, purple or orange, oversaturated colors, HDR halos.
```

## `things`

```text
A photorealistic photograph used as a background behind a band of large scrolling type. Ultra-wide 21:9 landscape.

Subject: a long row of storage: the front of a dark data-center rack filled with identical drive bays, or the receding aisle of an automated tape library, shot straight on so the identical slots repeat across the whole width of the frame like a texture.

Light: almost no light. Tiny status LEDs on each bay, most of them cool cyan (#46e3ff), a few scattered electric yellow-green (#d4ff3a). The LEDs are the only light source and throw a faint glow on the nearest metal edges.

Composition: the repeating pattern fills the frame edge to edge with no focal point, very even. The center horizontal band is darker and quieter than the top and bottom. Shallow depth of field: everything is slightly soft, LEDs become small round bokeh.

Camera: 50mm, f/1.4, focus slightly in front of the rack. 16-bit, clean shadows.

Finish: near-black (#060608), calm, restrained.

Avoid: text, labels, logos, numbers, people, cables in chaos, red or orange LEDs, purple, motion blur, sci-fi glow, smoke.
```

## `checksum`

```text
A photorealistic studio macro photograph for a full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: a single human fingerprint, pressed onto a sheet of black polished glass, photographed at extreme magnification so the ridges, pores and whorls become a landscape of fine curved lines.

Light: grazing light skimming the glass from the right side, colored cool cyan (#46e3ff), so only the raised ridges catch light; at the center of the whorl, a small area of the ridges picks up electric yellow-green (#d4ff3a). The glass outside the print is pure black.

Composition: the fingerprint sits in the right half of the frame, partly cropped by the right edge, and falls off into darkness toward the left. The left 50% stays near-black (#060608) for a headline and paragraph. Low contrast overall; it must sit behind text.

Camera: 100mm macro, f/8, focus stacked, medium-format, 16-bit, clean.

Finish: deep blacks, precise, calm, forensic but beautiful.

Avoid: text, numbers, ink smudges, hands, skin, scanners, padlocks, UI overlays, purple, watermarks.
```

## `tile-fingerprint`

```text
A photorealistic high-speed photograph for a small card background on a website. 4:3 landscape.

Subject: a single small water droplet has just struck a perfectly still, mirror-black water surface. One crown of ripples spreads outward in clean concentric rings, the rest of the surface untouched: one tiny change, a completely different surface.

Light: a thin ring of cool cyan (#46e3ff) light reflected along the ripple crests; the impact point carries a tiny electric yellow-green (#d4ff3a) highlight. The water is otherwise pure black.

Composition: the impact point sits in the lower right third; the ripples extend toward the edges and fade. The top and left of the frame stay near-black (#060608) and very quiet, because two input fields and two hex digests sit on top.

Camera: 100mm macro, f/11, 1/20000 s strobe freeze, low angle (about 15 degrees above the surface), 16-bit, clean.

Finish: minimal, calm, premium, crushed blacks.

Avoid: text, splashes with many droplets, colored water, bubbles, foam, reflections of a room, purple, watermarks.
```

## `why`

```text
A photorealistic studio macro photograph for a subtle full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: a cluster of perfectly clear natural quartz crystals, long hexagonal points with sharp faces, lying on black, photographed close enough that the internal facets and edges form clean geometric lines. It should suggest a modern, hard, flawless structure.

Light: two narrow lights: a cool cyan (#46e3ff) edge light from the upper left tracing the crystal edges, and a small electric yellow-green (#d4ff3a) refraction caught inside one crystal point near the upper right. No other light; black everywhere else.

Composition: the crystals occupy the top edge of the frame, partly cropped, and dissolve into darkness downward. At least 65% of the frame is near-black (#060608): a grid of text cards sits on top.

Camera: 100mm macro, f/8, focus stacked, medium-format, 16-bit, clean.

Finish: deep blacks, quiet, exact, premium.

Avoid: text, padlocks, shields, keys, rainbow dispersion, purple or pink, sparkle stars, mystical or crystal-healing styling, smoke, watermarks.
```

## `tile-fast`

```text
A photorealistic night photograph for a small card background on a website. 4:3 landscape.

Subject: a single branching lightning bolt over a completely dark, flat horizon: one bright main channel splitting into many fine branches, like a tree drawn in light in a fraction of a second.

Light: the main channel is an intense white core with an electric yellow-green (#d4ff3a) cast; the fine branches fade to cool cyan (#46e3ff). The sky around it is near-black, with only a faint cyan glow close to the bolt. No clouds lit up, no rain.

Composition: the bolt sits in the right half, its branches reaching toward the lower right corner; the top-left 50% stays near-black (#060608) for a very large number and a headline. Clean horizon line very low in the frame.

Camera: 24mm, f/8, 20-second exposure on a tripod, 16-bit, clean shadows, no noise.

Finish: calm despite the subject; precise, rare, crushed blacks.

Avoid: text, multiple bolts, storm clouds, rain, cities, people, purple or magenta tint (lightning is often purple: keep it white, yellow-green and cyan), motion streaks, watermarks.
```

## `how`

```text
A photorealistic backlit macro photograph for a subtle full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: the skeleton of a single leaf, all soft tissue gone, only the lace of veins left: thousands of fine veinlets join into smaller veins, the veins into larger ones, and all into one central midrib: a natural Merkle tree. Seen flat, filling the frame, slightly rotated.

Light: lit from behind on black so only the veins glow. The finest veinlets glow cool cyan (#46e3ff), the larger veins warm toward electric yellow-green (#d4ff3a), and the midrib carries the brightest yellow-green. No other light.

Composition: the leaf is very large, cropped on all sides, so it reads as a texture. Very dim overall: at least 60% of the frame near-black (#060608); the brightest part is the midrib running near the top. A diagram card sits over the center.

Camera: 100mm macro, f/11, focus stacked, medium-format, 16-bit, clean.

Finish: calm, organic, precise, premium.

Avoid: text, a whole tree, branches with bark, green chlorophyll color, autumn colors, purple, dew drops, fantasy glow, watermarks.
```

## `news`

```text
A photorealistic landscape photograph for a subtle full-width section background on a developer-tool website. Wide 16:9 landscape.

Subject: a dark, flat salt plain or calm lake under a cloudless sky in the last minutes of blue hour, with a single thin line of first light along the far horizon: the moment before the next day starts.

Light: the sky gradient is near-black at the top, deepening to a dim cool cyan (#46e3ff) close to the horizon; the horizon line itself is a razor-thin streak of electric yellow-green (#d4ff3a) light. The ground reflects a faint copy of that line.

Composition: horizon very low, at about 85% of the frame height; the upper 80% is near-black sky (#060608) with no stars. A grid of news cards sits on top.

Camera: 35mm, f/8, tripod, 16-bit, clean shadows, no noise.

Finish: quiet, minimal, calm, crushed blacks.

Avoid: text, sun disk, clouds, mountains, people, buildings, orange or pink sunrise colors, stars, purple, watermarks.
```

## `tile-news`

```text
A photorealistic macro photograph for a card background on a website. 16:10 landscape.

Subject: the edge of a freshly manufactured silicon wafer, its surface covered in a fine grid of identical rectangular dies, seen at a low angle so the grid recedes; one die near the upper right catches light as if it were the newest.

Light: a cool cyan (#46e3ff) raking light reveals the grid lines; that one die carries a bright electric yellow-green (#d4ff3a) reflection. Everything else falls to black.

Composition: the lit region sits in the upper right third; the left half and bottom stay near-black (#060608) for a large headline, a paragraph and a big number.

Camera: 100mm macro, f/5.6, tilt lens for a narrow diagonal plane of focus, medium-format, 16-bit, clean.

Finish: calm, precise, premium, crushed blacks.

Avoid: text, logos, rainbow thin-film colors (keep reflections cyan and yellow-green only), purple, tweezers, hands, watermarks.
```

## `install`

```text
A photorealistic night landscape photograph for the closing section of a developer-tool website. Wide 16:9 landscape.

Subject: a quiet aurora over a perfectly still, dark lake with a low, flat, featureless shoreline. The aurora forms one long, calm, smooth ribbon arcing across the sky from left to right, with fine vertical curtain rays, and is mirrored in the water.

Light: the aurora is cool cyan (#46e3ff) along its upper edge and an electric yellow-green (#d4ff3a) at its lower, brightest edge. No other light: no moon, no town, very few faint stars.

Composition: the ribbon sits in the upper half and the reflection in the lower; the center of the frame, where a centered headline and an install command sit, is the darkest and calmest part, with the ribbon passing above and around it. Symmetric, balanced, lots of near-black (#060608).

Camera: 20mm, f/1.8, 8-second exposure on a tripod, 16-bit, clean shadows, no noise.

Finish: calm, cinematic, premium, crushed blacks.

Avoid: text, people, tents, trees in the foreground, mountains with snow, red or purple aurora, the Milky Way, lens flare, watermarks.
```
