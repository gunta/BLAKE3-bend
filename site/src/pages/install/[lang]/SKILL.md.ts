/** Each language's SKILL.md, raw, beside its guide: /install/<slug>/SKILL.md (src/skills/). */
import type { APIRoute } from 'astro';
import { GUIDES, guide } from '../../../lib/guides';

export function getStaticPaths() {
  return GUIDES.map((g) => ({ params: { lang: g.slug } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(guide(params['lang'] ?? '').skill, { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
