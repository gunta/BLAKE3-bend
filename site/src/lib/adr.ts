/**
 * The architecture decision records in ../adr, read at build time so each
 * technique in results.json links to its ADR by number ("0002") without the
 * file names being copied into the site.
 */
import { blobUrl, treeUrl } from './site';

export interface Adr {
  number: string;
  file: string;
  /** The file name without its number: a stable anchor, e.g. "files-past-4-tib". */
  slug: string;
  title: string | undefined;
  date: string | undefined;
  status: string | undefined;
  url: string;
}

const sources = import.meta.glob<string>('../../../adr/[0-9][0-9][0-9][0-9]-*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function field(text: string, name: string): string | undefined {
  return new RegExp(`^${name}:\\s*(.+)$`, 'mi').exec(text)?.[1]?.trim();
}

const byNumber = new Map<string, Adr>();
for (const [path, text] of Object.entries(sources)) {
  const file = path.split('/').pop() ?? path;
  const number = file.slice(0, 4);
  const heading = /^#\s+(?:ADR\s+\d+\s*:\s*)?(.+)$/m.exec(text)?.[1]?.trim();
  byNumber.set(number, {
    number,
    file,
    slug: file.slice(5).replace(/\.md$/, ''),
    title: heading,
    date: field(text, 'Date'),
    status: field(text, 'Status'),
    url: blobUrl(`adr/${file}`),
  });
}

/** The ADR with this number, or a stand-in that links to the ADR directory. */
export function adr(number: string): Adr {
  return (
    byNumber.get(number) ?? {
      number,
      file: '',
      slug: number,
      title: undefined,
      date: undefined,
      status: undefined,
      url: treeUrl('adr'),
    }
  );
}

/** Every ADR in ../adr, in number order. */
export const allAdrs: Adr[] = [...byNumber.values()].sort((a, b) => a.number.localeCompare(b.number));

export const ADR_INDEX_URL = blobUrl('adr/README.md');
