/**
 * The brand in code: the mark's geometry and the palette, shared by the Logo
 * component, the favicon and app icon routes, and the Open Graph card.
 * BRAND.md explains the choices.
 */

export const COLORS = {
  void: '#060608',
  surface: '#0c0c11',
  surface2: '#14141b',
  ink: '#f4f3ee',
  ink2: '#b8b7c4',
  ink3: '#8f8e9e',
  volt: '#d4ff3a',
  voltInk: '#0b0e00',
  ion: '#46e3ff',
  plasma: '#ff4f8b',
} as const;

/** One stroke of the mark: a polyline, width in viewBox units. */
export interface MarkPath {
  d: string;
  w: number;
}

const leaf = 3.6;
const mid = 4.6;
const root = 5.6;

/**
 * The Merge, in a 64-unit box: four leaves of uneven length merge into two
 * nodes at x=29, those into the root at x=45, and a short stem runs on to the
 * digest dot. Drawn upright, then leaned forward by MARK_SKEW.
 */
export const MARK_PATHS: readonly MarkPath[] = [
  { d: 'M15 12 L23 12 L29 18', w: leaf },
  { d: 'M6 24 L23 24 L29 18', w: leaf },
  { d: 'M6 40 L23 40 L29 46', w: leaf },
  { d: 'M15 52 L23 52 L29 46', w: leaf },
  { d: 'M29 18 L33 18 L45 32', w: mid },
  { d: 'M29 46 L33 46 L45 32', w: mid },
  { d: 'M45 32 L49 32', w: root },
];

/** Lean the lines 10 degrees forward around the root's row (y = 32), so the root and dot stay put. */
export const MARK_SKEW = `translate(${(32 * Math.tan((10 * Math.PI) / 180)).toFixed(3)} 0) skewX(-10)`;

export const MARK_DOT = { cx: 54.5, cy: 32, r: 5.8 } as const;

/** Tight box around the leaned mark, for inline use next to text. */
export const MARK_VIEWBOX = '2 9.5 59 45';

/** The mark as standalone SVG markup, e.g. for the favicon and the OG card. */
export function markSvg(opts: { stroke: string; dot?: string; bold?: number }): string {
  const bold = opts.bold ?? 1;
  const paths = MARK_PATHS.map((p) => `<path d="${p.d}" stroke-width="${(p.w * bold).toFixed(2)}"/>`).join('');
  const r = MARK_DOT.r * (bold > 1 ? 1 + (bold - 1) * 0.45 : 1);
  return (
    `<g fill="none" stroke="${opts.stroke}" stroke-linecap="round" stroke-linejoin="round" transform="${MARK_SKEW}">${paths}</g>` +
    `<circle cx="${(49 + r * 0.95).toFixed(2)}" cy="${MARK_DOT.cy}" r="${r.toFixed(2)}" fill="${opts.dot ?? opts.stroke}"/>`
  );
}

/** The app icon: a volt tile with the bold mark in near-black, like a race number plate. */
export function iconSvg(size = 64): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="${COLORS.volt}"/>
<g transform="translate(32 32) scale(0.74) translate(-32.4 -32)">${markSvg({ stroke: COLORS.voltInk, bold: 1.45 })}</g>
</svg>`;
}
