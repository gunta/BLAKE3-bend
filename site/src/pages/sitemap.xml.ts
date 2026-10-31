/** Every page, for search engines (submit it in Search Console: a project site has no robots.txt of its own). */
import type { APIRoute } from 'astro';
import { GUIDES } from '../lib/guides';
import { absoluteUrl } from '../lib/site';

const pages = ['', 'install/', ...GUIDES.map((g) => `install/${g.slug}/`), 'languages/', 'benchmarks/', 'gpu/', 'changelog/'];

export const GET: APIRoute = ({ site }) =>
  new Response(
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${pages
      .map((p) => `  <url><loc>${absoluteUrl(p, site)}</loc></url>`)
      .join('\n')}\n</urlset>\n`,
    { headers: { 'Content-Type': 'application/xml' } },
  );
