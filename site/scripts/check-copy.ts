// Checks the built site's text for ADR numbers and the words "decision
// record" (BRAND.md: readers get headlines and dates; the write-up is a link).
// Runs after `astro build`, over every page and the RSS feed, so copy from
// results.json is caught as well as copy in the pages.
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const dist = new URL('../dist/', import.meta.url).pathname;
const banned = /\bADR[ -]?\d{4}|decision records?/gi;

function* files(dir: string): Generator<string> {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, e.name);
    if (e.isDirectory()) yield* files(path);
    else if (/\.(html|xml)$/.test(e.name)) yield path;
  }
}

/** The text a reader sees: no scripts, styles or tags, so links to adr/ files pass. */
const text = (src: string) =>
  src
    .replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

let found = 0;
let checked = 0;
for (const path of files(dist)) {
  checked++;
  const t = text(readFileSync(path, 'utf8'));
  for (const m of t.matchAll(banned)) {
    found++;
    const at = m.index ?? 0;
    console.error(`${relative(dist, path)}: "${m[0]}" in …${t.slice(Math.max(0, at - 60), at + 60).trim()}…`);
  }
}
console.log(`${checked} files checked, ${found} ADR mentions in the copy`);
process.exit(found ? 1 : 0);
