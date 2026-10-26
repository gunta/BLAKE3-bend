/**
 * The changelog as RSS 2.0, one item per story, linked from every page's
 * <head> so feed readers find it.
 */
import type { APIRoute } from 'astro';
import { stories } from '../../lib/news';
import { SITE_NAME, absoluteUrl } from '../../lib/site';

const escape = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export const GET: APIRoute = ({ site }) => {
  const page = absoluteUrl('changelog/', site);
  const items = stories.map((s) => {
    const link = `${page}#${s.slug}`;
    const body = [s.dek, s.stat && `${s.stat.value}: ${s.stat.label}.`, ...s.points.map((p) => `${p}.`)].filter(Boolean).join(' ');
    const date = Date.parse(s.date);
    return [
      '<item>',
      `<title>${escape(s.headline)}</title>`,
      `<link>${escape(link)}</link>`,
      `<guid isPermaLink="true">${escape(link)}</guid>`,
      s.tag ? `<category>${escape(s.tag)}</category>` : '',
      Number.isNaN(date) ? '' : `<pubDate>${new Date(date).toUTCString()}</pubDate>`,
      `<description>${escape(body)}</description>`,
      '</item>',
    ].join('');
  });
  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0"><channel>',
    `<title>${SITE_NAME}: what's new</title>`,
    `<link>${escape(page)}</link>`,
    '<description>Every speed-up, new platform and proof in turboblake, BLAKE3 turbocharged.</description>',
    '<language>en</language>',
    ...items,
    '</channel></rss>',
  ].join('\n');
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
};
