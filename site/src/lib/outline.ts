/**
 * Text as SVG outlines in the brand's own fonts, for images rendered at build
 * time (the Open Graph card): librsvg cannot load web fonts, so the glyphs are
 * drawn as paths instead. Also the width of a label, for sizing a column to it. The fonts are the same variable WOFF2 files the page
 * serves (Geist, Geist Mono), decompressed and instanced at the requested weight.
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import * as fontkit from 'fontkit';
import { decompress } from 'wawoff2';

const require = createRequire(import.meta.url);

const FILES = {
  sans: '@fontsource-variable/geist/files/geist-latin-wght-normal.woff2',
  mono: '@fontsource-variable/geist-mono/files/geist-mono-latin-wght-normal.woff2',
} as const;

export type Face = keyof typeof FILES;

const cache = new Map<string, Promise<fontkit.Font>>();

function load(face: Face, wght: number): Promise<fontkit.Font> {
  const key = `${face}:${wght}`;
  let font = cache.get(key);
  if (!font) {
    font = (async () => {
      const ttf = Buffer.from(await decompress(readFileSync(require.resolve(FILES[face]))));
      const base = fontkit.create(ttf) as fontkit.Font;
      return base.getVariation({ wght });
    })();
    cache.set(key, font);
  }
  return font;
}

export interface OutlineOptions {
  face?: Face;
  size: number;
  wght?: number;
  /** Extra space between letters, in em. */
  tracking?: number;
}

/** The advance width of `text` in em: how wide it sets at any font size. */
export async function textEm(text: string, opts: { face?: Face; wght?: number } = {}): Promise<number> {
  const font = await load(opts.face ?? 'sans', opts.wght ?? 400);
  return font.layout(text).advanceWidth / font.unitsPerEm;
}

/** Outlines of `text` with its baseline at the origin; `width` is the advance in px. */
export async function outline(text: string, opts: OutlineOptions): Promise<{ d: string; width: number }> {
  const font = await load(opts.face ?? 'sans', opts.wght ?? 600);
  const scale = opts.size / font.unitsPerEm;
  const run = font.layout(text);
  const tracking = (opts.tracking ?? 0) * font.unitsPerEm;
  let x = 0;
  let d = '';
  run.glyphs.forEach((glyph, i) => {
    const pos = run.positions[i]!;
    const path = glyph.path.scale(scale, -scale).translate((x + pos.xOffset) * scale, -pos.yOffset * scale);
    d += path.toSVG();
    x += pos.xAdvance + tracking;
  });
  return { d, width: (x - tracking) * scale };
}
