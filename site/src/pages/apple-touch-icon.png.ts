/** The 180 x 180 home-screen icon, rasterized from the same tile as the favicon. */
import type { APIRoute } from 'astro';
import sharp from 'sharp';
import { iconSvg } from '../lib/brand';

export const GET: APIRoute = async () => {
  // iOS rounds the corners itself, so the tile goes edge to edge.
  const svg = iconSvg(180).replace('rx="14"', 'rx="0"');
  const png = await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toBuffer();
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png' },
  });
};
