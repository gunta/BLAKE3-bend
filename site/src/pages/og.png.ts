/**
 * The Open Graph card (1200 x 630 PNG), drawn at build time from the same
 * headlines as the page, so a link preview never shows stale numbers.
 */
import type { APIRoute } from 'astro';
import sharp from 'sharp';
import { headlines, machineName } from '../lib/page';
import { SITE_TITLE } from '../lib/site';

const W = 1200;
const H = 630;

function esc(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** Largest font size (px) at which `text` should fit in `width`, from an average glyph width. */
function fit(text: string, width: number, max: number, em = 0.56): number {
  return Math.max(14, Math.min(max, Math.floor(width / (Math.max(1, text.length) * em))));
}

function card(): string {
  const stats = [headlines.gpu, headlines.cli, headlines.perCore].filter((h) => h !== undefined);
  const colW = (W - 160) / Math.max(1, stats.length);
  const font = `font-family="Helvetica Neue, Helvetica, Arial, DejaVu Sans, Liberation Sans, sans-serif"`;
  const columns = stats
    .map((h, i) => {
      const x = 80 + i * colW;
      const w = colW - 40;
      const fill = i === 0 ? '#ff8a5c' : '#f0efec';
      const value = h.value.replace(/^up to /, '');
      return `
      <rect x="${x}" y="300" width="${w}" height="4" rx="2" fill="${i === 0 ? '#eb6834' : '#3987e5'}"/>
      <text x="${x}" y="408" ${font} font-size="${fit(value, w, 104, 0.6)}" font-weight="700" letter-spacing="-3" fill="${fill}">${esc(value)}</text>
      <text x="${x}" y="458" ${font} font-size="${fit(h.short, w, 28, 0.58)}" font-weight="600" fill="#f0efec">${esc(h.short)}</text>
      <text x="${x}" y="496" ${font} font-size="${fit(h.context, w, 26)}" fill="#a3a29a">${esc(h.context)}</text>`;
    })
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#0d0d0d"/>
  <rect x="80" y="80" width="56" height="56" rx="14" fill="#f0efec"/>
  <rect x="92" y="95" width="31.5" height="7" rx="3.5" fill="#0d0d0d"/>
  <rect x="92" y="104.5" width="21" height="7" rx="3.5" fill="#0d0d0d"/>
  <rect x="92" y="114" width="11.5" height="7" rx="3.5" fill="#eb6834"/>
  <text x="160" y="124" ${font} font-size="48" font-weight="700" letter-spacing="-1" fill="#f0efec">${esc(SITE_TITLE)}</text>
  <text x="80" y="210" ${font} font-size="32" fill="#c3c2b7">Raced against the official Rust/C BLAKE3 on ${esc(machineName)}.</text>
  <text x="80" y="254" ${font} font-size="32" fill="#c3c2b7">Wins, ties and the floors, from the benchmark data.</text>
  ${columns}
  <text x="80" y="566" ${font} font-size="24" fill="#a3a29a">gunta.github.io/BLAKE3-bend</text>
</svg>`;
}

export const GET: APIRoute = async () => {
  const png = await sharp(Buffer.from(card())).png({ compressionLevel: 9 }).toBuffer();
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
