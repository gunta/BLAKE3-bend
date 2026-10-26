/**
 * The changelog: every ADR in ../adr told as news, newest first. The words
 * (headline, dek, stat, points) come from results.json techniques, so the
 * numbers keep one source; an ADR with no entry there still appears, under
 * its own title. ADR numbers stay internal: readers get headlines and dates.
 */
import { allAdrs } from './adr';
import { results, type Technique } from './results';
import { withBase } from './site';

export type Tag = NonNullable<Technique['tag']>;

export interface Story {
  /** The anchor on the changelog page, from the ADR's file name. */
  slug: string;
  /** The ADR's number: for keys and lookups, never shown. */
  number: string;
  /** ISO 8601, with the time when results.json has one. */
  date: string;
  /** "Oct 26, 2026" */
  day: string;
  tag: Tag | undefined;
  headline: string;
  dek: string | undefined;
  stat: Technique['stat'];
  points: string[];
  /** The changelog entry on this site. */
  href: string;
  /** The full engineering write-up (the ADR) on GitHub. */
  writeUp: string;
}

const dayFormat = new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });

/** The calendar day as written (the date's own YYYY-MM-DD), not shifted to UTC. */
function day(iso: string): string {
  const ymd = /^\d{4}-\d{2}-\d{2}/.exec(iso)?.[0];
  return ymd ? dayFormat.format(new Date(`${ymd}T00:00:00Z`)) : iso;
}

const techniques = new Map(results.techniques.map((t) => [t.adr, t]));

export const stories: Story[] = allAdrs
  .map((a) => {
    const t = techniques.get(a.number);
    const date = t?.date ?? a.date ?? '';
    return {
      slug: a.slug,
      number: a.number,
      date,
      day: day(date),
      tag: t?.tag,
      headline: t?.headline ?? a.title ?? t?.title ?? a.slug,
      dek: t?.dek,
      stat: t?.stat,
      points: t?.points ?? [],
      href: withBase(`changelog/#${a.slug}`),
      writeUp: a.url,
    };
  })
  .sort((a, b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0) || b.number.localeCompare(a.number));

/** The story an ADR is told in, for links from other pages. */
export function story(number: string): Story | undefined {
  return stories.find((s) => s.number === number);
}

export const latest = stories[0];
