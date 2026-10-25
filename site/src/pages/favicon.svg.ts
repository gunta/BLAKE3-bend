/** The favicon: the app icon tile, drawn from the brand geometry. */
import type { APIRoute } from 'astro';
import { iconSvg } from '../lib/brand';

export const GET: APIRoute = () =>
  new Response(iconSvg(), {
    headers: { 'Content-Type': 'image/svg+xml' },
  });
