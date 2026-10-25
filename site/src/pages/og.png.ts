/**
 * The Open Graph card (1200 x 630 PNG), drawn at build time from the same
 * headlines as the page, so a link preview never shows stale numbers. Text is
 * outlined in the brand fonts (src/lib/outline.ts); the tree is the hero's.
 */
import type { APIRoute } from 'astro';
import sharp from 'sharp';
import { COLORS, markSvg } from '../lib/brand';
import { headlines, machineName, type Headline } from '../lib/page';
import { outline } from '../lib/outline';
import { treePaths } from '../lib/tree';

const W = 1200;
const H = 630;
const PAD = 72;

/** Shrink a size until `text` fits `width`, measuring the real outlines. */
async function fitted(text: string, width: number, opts: Parameters<typeof outline>[1]) {
  let o = await outline(text, opts);
  if (o.width > width) o = await outline(text, { ...opts, size: Math.floor((opts.size * width) / o.width) });
  return o;
}

async function card(): Promise<string> {
  const lead = headlines.models ?? headlines.gpu ?? headlines.cli;
  const rest = [headlines.gpu, headlines.cli, headlines.perCore].filter((h): h is Headline => h !== undefined && h !== lead).slice(0, 3);

  // B3ND, with the 3 in volt: three runs so the middle one can take its own color.
  const wordOpts = { face: 'italic', size: 40, wdth: 125, wght: 850 } as const;
  const w1 = await outline('B', wordOpts);
  const w2 = await outline('3', wordOpts);
  const w3 = await outline('ND', wordOpts);
  const tag = await outline('BLAKE3 IN BEND2', { face: 'mono', size: 15, wdth: 90, wght: 400, tracking: 0.06 });

  const big = lead ? await fitted(lead.value.replace(/^up to /, '').replace(/x$/, '×'), 640, { face: 'italic', size: 200, wdth: 125, wght: 840, tracking: -0.03 }) : undefined;
  const what = lead ? await fitted(lead.short, 560, { size: 34, wdth: 112, wght: 700 }) : undefined;
  const where = lead ? await fitted(lead.context, 600, { size: 24, wdth: 100, wght: 500 }) : undefined;
  const site = await outline('gunta.github.io/BLAKE3-bend', { face: 'mono', size: 18, wdth: 90, wght: 400 });
  const ran = await fitted(`Raced against the official Rust/C on ${machineName}`, 520, { face: 'mono', size: 15, wdth: 90, wght: 400 });

  const cols = await Promise.all(
    rest.map(async (h) => {
      // "up to 10.7x" keeps the figure big and moves the qualifier into the label.
      const upTo = /^up to /.test(h.value);
      return {
        value: await fitted(h.value.replace(/^up to /, '').replace(/x$/, '×'), 260, { face: 'italic', size: 46, wdth: 125, wght: 820, tracking: -0.03 }),
        label: await fitted(upTo ? `${h.short}, best case` : h.short, 270, { size: 17, wdth: 100, wght: 600 }),
      };
    }),
  );

  const { edges, root } = treePaths({ x0: 560, rootX: 1040, y: 300, half: 230 });
  const tree = edges
    .map((e) => `<path d="${e.d}" stroke-width="${(1.4 + e.level * 0.7).toFixed(1)}" stroke-opacity="${(0.35 + e.level * 0.15).toFixed(2)}"/>`)
    .join('');

  const colW = 300;
  const statY = 548;
  const stats = cols
    .map(
      (c, i) => `<g transform="translate(${PAD + i * colW} ${statY})">
        <path d="${c.value.d}" fill="${i === 0 ? COLORS.ion : COLORS.ink}"/>
        <path transform="translate(0 30)" d="${c.label.d}" fill="${COLORS.ink3}"/>
      </g>`,
    )
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="heat" x1="560" y1="0" x2="1100" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${COLORS.ion}"/><stop offset="0.75" stop-color="${COLORS.volt}"/>
    </linearGradient>
    <linearGradient id="markheat" x1="4" y1="0" x2="60" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${COLORS.ion}"/><stop offset="0.62" stop-color="${COLORS.volt}"/><stop offset="1" stop-color="#f1ffc2"/>
    </linearGradient>
    <radialGradient id="flare"><stop offset="0" stop-color="#fff"/><stop offset="0.2" stop-color="${COLORS.volt}" stop-opacity="0.9"/><stop offset="1" stop-color="${COLORS.volt}" stop-opacity="0"/></radialGradient>
    <linearGradient id="fadeL" x1="0" y1="0" x2="1" y2="0"><stop offset="0.35" stop-color="${COLORS.void}"/><stop offset="0.62" stop-color="${COLORS.void}" stop-opacity="0"/></linearGradient>
    <filter id="glow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="5"/></filter>
  </defs>
  <rect width="${W}" height="${H}" fill="${COLORS.void}"/>
  <g fill="none" stroke="url(#heat)" stroke-linecap="round">
    <g filter="url(#glow)" opacity="0.7">${tree}</g>
    ${tree}
  </g>
  <path d="M${root.x} ${root.y}H${W}" stroke="${COLORS.volt}" stroke-width="3" stroke-dasharray="14 7 5 7 22 7"/>
  <circle cx="${root.x}" cy="${root.y}" r="90" fill="url(#flare)"/>
  <rect width="${W}" height="${H}" fill="url(#fadeL)"/>

  <g transform="translate(${PAD} ${PAD - 8}) scale(0.86)">${markSvg({ stroke: 'url(#markheat)' })}</g>
  <g transform="translate(${PAD + 66} ${PAD + 27})">
    <path d="${w1.d}" fill="${COLORS.ink}"/>
    <path transform="translate(${w1.width} 0)" d="${w2.d}" fill="${COLORS.volt}"/>
    <path transform="translate(${w1.width + w2.width} 0)" d="${w3.d}" fill="${COLORS.ink}"/>
    <rect x="${w1.width + w2.width + w3.width + 18}" y="-26" width="1" height="28" fill="${COLORS.ink}" fill-opacity="0.2"/>
    <path transform="translate(${w1.width + w2.width + w3.width + 34} -7)" d="${tag.d}" fill="${COLORS.ink3}"/>
  </g>
  <path transform="translate(${PAD} ${PAD + 62})" d="${ran.d}" fill="${COLORS.ink3}"/>

  ${big ? `<path transform="translate(${PAD - 6} 352)" d="${big.d}" fill="${COLORS.volt}"/>` : ''}
  ${what ? `<path transform="translate(${PAD} 404)" d="${what.d}" fill="${COLORS.ink}"/>` : ''}
  ${where ? `<path transform="translate(${PAD} 442)" d="${where.d}" fill="${COLORS.ink2}"/>` : ''}

  <rect x="${PAD}" y="484" width="${W - PAD * 2}" height="1" fill="${COLORS.ink}" fill-opacity="0.12"/>
  ${stats}
  <path transform="translate(${W - PAD - site.width} ${PAD + 16})" d="${site.d}" fill="${COLORS.ink3}"/>
</svg>`;
}

export const GET: APIRoute = async () => {
  const png = await sharp(Buffer.from(await card())).png({ compressionLevel: 9 }).toBuffer();
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
