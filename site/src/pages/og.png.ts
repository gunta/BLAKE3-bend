/**
 * The Open Graph card (1200 x 630 PNG), drawn at build time from the same
 * data as the page, so a link preview never shows stale numbers. Text is
 * outlined in the brand fonts (src/lib/outline.ts); the tree is the hero's.
 */
import type { APIRoute } from 'astro';
import sharp from 'sharp';
import { COLORS, markSvg } from '../lib/brand';
import { heroProof } from '../lib/page';
import { outline } from '../lib/outline';
import { INSTALL } from '../lib/site';
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
  // The wordmark: "turbo" in volt, "blake" in ink, as on the page.
  const w1 = await outline('turbo', { size: 40, wght: 700, tracking: -0.045 });
  const w2 = await outline('blake', { size: 40, wght: 700, tracking: -0.045 });
  const tag = await outline('BLAKE3, turbocharged', { size: 20, wght: 450 });

  // Both headline lines at one size: the size at which the longer one fits.
  const lines = ['Checksum anything', 'at the speed of your SSD.'];
  const natural = await Promise.all(lines.map((l) => outline(l, { size: 76, wght: 650, tracking: -0.05 })));
  const size = Math.min(76, Math.floor((76 * 720) / Math.max(...natural.map((o) => o.width))));
  const [h1a, h1b] = await Promise.all(lines.map((l) => outline(l, { size, wght: 650, tracking: -0.05 })));
  const proof = heroProof
    ? await fitted(
        `${heroProof.size ?? 'A huge'} model checked in ${heroProof.seconds} s, ${heroProof.ratio.replace(/x$/, '×')} faster than ${heroProof.baseline}`,
        700,
        { size: 26, wght: 450 },
      )
    : undefined;
  const cmd = await outline(`$ ${INSTALL}`, { face: 'mono', size: 22, wght: 450 });
  const site = await outline('gunta.github.io/turboblake', { face: 'mono', size: 18, wght: 400 });

  const { edges, root } = treePaths({ x0: 600, rootX: 1060, y: 300, half: 220 });
  const tree = edges
    .map((e) => `<path d="${e.d}" stroke-width="${(1.2 + e.level * 0.6).toFixed(1)}" stroke-opacity="${(0.3 + e.level * 0.14).toFixed(2)}"/>`)
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="heat" x1="600" y1="0" x2="1100" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${COLORS.ion}"/><stop offset="0.75" stop-color="${COLORS.volt}"/>
    </linearGradient>
    <linearGradient id="markheat" x1="4" y1="0" x2="60" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${COLORS.ion}"/><stop offset="0.62" stop-color="${COLORS.volt}"/><stop offset="1" stop-color="#f1ffc2"/>
    </linearGradient>
    <linearGradient id="h1grad" x1="${PAD}" y1="0" x2="${PAD + 700}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ededef"/><stop offset="1" stop-color="${COLORS.volt}"/>
    </linearGradient>
    <radialGradient id="flare"><stop offset="0" stop-color="#fff"/><stop offset="0.2" stop-color="${COLORS.volt}" stop-opacity="0.85"/><stop offset="1" stop-color="${COLORS.volt}" stop-opacity="0"/></radialGradient>
    <linearGradient id="fadeL" x1="0" y1="0" x2="1" y2="0"><stop offset="0.4" stop-color="${COLORS.void}"/><stop offset="0.7" stop-color="${COLORS.void}" stop-opacity="0"/></linearGradient>
    <filter id="glow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="5"/></filter>
  </defs>
  <rect width="${W}" height="${H}" fill="${COLORS.void}"/>
  <g fill="none" stroke="url(#heat)" stroke-linecap="round">
    <g filter="url(#glow)" opacity="0.6">${tree}</g>
    ${tree}
  </g>
  <path d="M${root.x} ${root.y}H${W}" stroke="${COLORS.volt}" stroke-width="2.5" stroke-dasharray="14 7 5 7 22 7" opacity="0.8"/>
  <circle cx="${root.x}" cy="${root.y}" r="80" fill="url(#flare)"/>
  <rect width="${W}" height="${H}" fill="url(#fadeL)"/>

  <g transform="translate(${PAD} ${PAD - 10}) scale(0.78)">${markSvg({ stroke: 'url(#markheat)' })}</g>
  <g transform="translate(${PAD + 60} ${PAD + 24})">
    <path d="${w1.d}" fill="${COLORS.volt}"/>
    <path transform="translate(${w1.width} 0)" d="${w2.d}" fill="${COLORS.ink}"/>
    <rect x="${w1.width + w2.width + 18}" y="-26" width="1" height="30" fill="${COLORS.ink}" fill-opacity="0.2"/>
    <path transform="translate(${w1.width + w2.width + 34} -3)" d="${tag.d}" fill="${COLORS.ink3}"/>
  </g>

  <path transform="translate(${PAD} 300)" d="${h1a!.d}" fill="#ededef"/>
  <path transform="translate(${PAD} ${300 + Math.round(size * 1.1)})" d="${h1b!.d}" fill="url(#h1grad)"/>
  ${proof ? `<path transform="translate(${PAD} 448)" d="${proof.d}" fill="${COLORS.ink2}"/>` : ''}

  <rect x="${PAD}" y="${H - PAD - 46}" width="${cmd.width + 36}" height="50" rx="10" fill="${COLORS.surface}" stroke="${COLORS.ink}" stroke-opacity="0.16"/>
  <path transform="translate(${PAD + 18} ${H - PAD - 14})" d="${cmd.d}" fill="${COLORS.ink}"/>
  <path transform="translate(${W - PAD - site.width} ${H - PAD - 14})" d="${site.d}" fill="${COLORS.ink3}"/>
</svg>`;
}

export const GET: APIRoute = async () => {
  const png = await sharp(Buffer.from(await card())).png({ compressionLevel: 9 }).toBuffer();
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
