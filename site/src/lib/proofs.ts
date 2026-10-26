/**
 * The laws Bend's checker proves, read from bend/LAWS.bend and bend/PROOF.bend
 * at build time and sorted into the groups the proofs section shows. Every law
 * in LAWS.bend must sit on exactly one card, and every name on a card must be a
 * law there, or the build fails: the page lists what `bend/prove.sh` checks.
 */
import { blobUrl } from './site';

const files = import.meta.glob<string>(['../../../bend/LAWS.bend', '../../../bend/PROOF.bend', '../../../bend/proof/*.bend'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

function source(name: string): string {
  const text = Object.entries(files).find(([path]) => path.endsWith(`/${name}`))?.[1];
  if (text === undefined) throw new Error(`site/src/lib/proofs.ts: bend/${name} not found`);
  return text;
}

const LAWS = source('LAWS.bend');
const PROOF = source('PROOF.bend');
/** The proof modules PROOF.bend imports (bend/proof/*.bend). */
const MODULES = Object.entries(files)
  .filter(([path]) => path.includes('/bend/proof/'))
  .map(([, text]) => text);

/** The names of the `law` blocks in a Bend file, in order. */
function lawNames(text: string): string[] {
  return [...text.matchAll(/^law\s+([\w.]+):/gm)].map((m) => m[1]!);
}

export type Scope = 'every-input' | 'every-size' | 'computed';

export interface LawCard {
  /** Law names in LAWS.bend; a trailing `*` takes every law with that prefix. */
  names: string[];
  claim: string;
  /** How much the law covers, in a few words. */
  covers: string;
}

export interface LawGroup {
  id: string;
  scope: Scope;
  title: string;
  blurb: string;
  cards: (LawCard & { laws: string[] })[];
}

const GROUPS: (Omit<LawGroup, 'cards'> & { cards: LawCard[] })[] = [
  {
    id: 'every-input',
    scope: 'every-input',
    title: 'For every input, on the code that runs',
    blurb: 'Stated about the defs in blake3.bend that b3sum and the benchmarks call, for all values of their arguments.',
    cards: [
      {
        names: ['compress8.lane'],
        claim:
          'Each of the eight lanes of compress8, the vectorized kernel that hashes the CPU tree’s full 8- and 32-chunk groups, is the scalar compression of that lane: no lane reads another lane’s words, the wrong message word in any round, or the wrong counter.',
        covers: 'every CV, block, counter and flag set: 2^6,275 inputs',
      },
      {
        names: ['par8.lane'],
        claim: 'Each lane of par8, a level of eight parent compressions at once, is the parent of the right two lanes.',
        covers: 'every pair of 8-lane CVs: 2^4,099 inputs',
      },
      {
        names: ['cpu.at', 'cpu.hash'],
        claim:
          'The CPU tree b3sum runs (eight chunks at once through compress8, 32-chunk leaves, node kinds from a U32 copy of the depth) is blake3.bend’s plain scalar tree, one chunk at a time: the same CV, bit for bit.',
        covers: 'every array, every span: any counter base, chunk count, last-chunk length and root flag',
      },
      {
        names: ['gpu.at', 'gpu.hash'],
        claim:
          'The GPU tree (whole 4-, 16- and 64-chunk subtrees to one lane each, bigger ones to strided lanes that read neighbouring memory) is the same scalar tree: the same CV, bit for bit.',
        covers: 'every array, every span, every lane layout up to 2^32 chunks',
      },
      {
        names: ['share.fork'],
        claim:
          'The copy of the input the laws hand each tree node is Array.fork’s own body, (a, a), so the laws are about the code that runs; what stays trusted is the runtime sharing one buffer for it.',
        covers: 'every array',
      },
      {
        names: ['schedule'],
        claim: 'The message permutation applied r times is row r of MSG_SCHEDULE in the official C code.',
        covers: 'every 64-byte block: 2^512 inputs',
      },
      {
        names: ['ob.hash', 'ob.at'],
        claim:
          'The tree that writes iroh’s bao outboard computes exactly the plain tree’s hash, so writing an outboard never changes a digest.',
        covers: 'every array, every length, every span',
      },
    ],
  },
  {
    id: 'every-size',
    scope: 'every-size',
    title: 'For every size, on BLAKE3’s tree',
    blurb:
      'About the shape of the tree, so they hold for any compression function. Inductions over the chunk count, not a sweep of sizes.',
    cards: [
      {
        names: ['segments'],
        claim:
          'A big file’s 1 GiB parts are complete subtrees but the last, so they hash apart, in parallel, and merge as parents into the same tree: b3sum’s path past 4 GiB.',
        covers: 'every file size and segment size',
      },
      {
        names: ['levels', 'levels.root'],
        claim: 'Pairing neighbours level by level, the odd one carried up, builds BLAKE3’s tree: a GPU-style reduction is exact.',
        covers: 'every chunk count',
      },
      {
        names: ['tree.leaves', 'tree.parents'],
        claim:
          'The tree over n chunks has n leaves and n − 1 parents: no chunk is dropped or hashed twice, and a blob of g chunk groups has g − 1 outboard pairs.',
        covers: 'every chunk count',
      },
      {
        names: ['stream.shape', 'stream.order'],
        claim:
          'The lazy merge stack that streamed the 101.5 GB model shard builds that same tree, with every segment once and in order, so a streamed hash is the mapped one.',
        covers: 'every segment count up to 2^32',
      },
    ],
  },
  {
    id: 'computed',
    scope: 'computed',
    title: 'Computed by the checker',
    blurb: 'Bend’s checker runs BLAKE3 itself (U32 is 32 Bools to it, about 0.6 s a compression) and compares the results.',
    cards: [
      {
        names: ['kat.*'],
        claim:
          'The official test vectors, through the CPU tree, the GPU tree, a GPU flat leaf, and two spans merged by a ROOT parent as b3sum merges a big file’s parts.',
        covers: '13 vectors, 0 to 8,193 bytes',
      },
      {
        names: ['consts.iv', 'consts.flags'],
        claim: 'The IV and the four domain flags are the C code’s constants, and the flags are distinct bits.',
        covers: 'read from c/blake3_impl.h',
      },
      {
        names: ['tree1.digits'],
        claim: 'blake3.bend’s split rule (n > 2^p) is the digit form the tree laws reason about.',
        covers: 'every input of 1 to 1,024 chunks',
      },
    ],
  },
];

function matches(pattern: string, name: string): boolean {
  return pattern.endsWith('*') ? name.startsWith(pattern.slice(0, -1)) : name === pattern;
}

function build(): LawGroup[] {
  const all = lawNames(LAWS);
  const placed = new Map<string, string>();
  const groups = GROUPS.map((g) => ({
    ...g,
    cards: g.cards.map((c) => {
      const laws = all.filter((n) => c.names.some((p) => matches(p, n)));
      for (const p of c.names) {
        if (!all.some((n) => matches(p, n))) {
          throw new Error(`site/src/lib/proofs.ts: "${p}" is not a law in bend/LAWS.bend`);
        }
      }
      for (const n of laws) {
        const other = placed.get(n);
        if (other) throw new Error(`site/src/lib/proofs.ts: law ${n} is on two cards (${other} and ${c.names.join(', ')})`);
        placed.set(n, c.names.join(', '));
      }
      return { ...c, laws };
    }),
  }));
  const missing = all.filter((n) => !placed.has(n));
  if (missing.length > 0) {
    throw new Error(`site/src/lib/proofs.ts: laws in bend/LAWS.bend not on any card: ${missing.join(', ')}`);
  }
  return groups;
}

export const lawGroups: LawGroup[] = build();

/** Laws stated in LAWS.bend, and the lemmas PROOF.bend proves on the way. */
export const lawCount = lawNames(LAWS).length;
/** Laws for every input or every size, as opposed to computed ones. */
export const universalCount = lawGroups
  .filter((g) => g.scope !== 'computed')
  .reduce((n, g) => n + g.cards.reduce((m, c) => m + c.laws.length, 0), 0);
export const lemmaCount = lawNames(PROOF).length + MODULES.reduce((n, text) => n + lawNames(text).length, 0);

/** A block of a Bend file: from its `law` or `def` line to the next blank line. */
function block(text: string, head: string, file: string): string {
  const start = text.indexOf(`\n${head}`);
  if (start < 0) throw new Error(`site/src/lib/proofs.ts: "${head}" not found in bend/${file}`);
  const end = text.indexOf('\n\n', start + 1);
  return text.slice(start + 1, end < 0 ? undefined : end);
}

/** The comment lines right above a block. */
function comment(text: string, head: string): string {
  const lines = text.slice(0, text.indexOf(`\n${head}`)).split('\n');
  const out: string[] = [];
  for (let i = lines.length - 1; i >= 0 && lines[i]!.startsWith('#'); i--) out.unshift(lines[i]!);
  return out.join('\n');
}

/** One law as LAWS.bend states it and PROOF.bend proves it, for the sample. */
export function sample(name: string): { law: string; proof: string } {
  const head = `law ${name}:`;
  const doc = comment(LAWS, head);
  return {
    law: [doc, block(LAWS, head, 'LAWS.bend')].filter(Boolean).join('\n'),
    proof: block(PROOF, `def Laws.${name}(`, 'PROOF.bend'),
  };
}

export const LAWS_URL = blobUrl('bend/LAWS.bend');
export const PROOF_URL = blobUrl('bend/PROOF.bend');
export const GENERATOR_URL = blobUrl('bend/tools/gen_laws.py');
