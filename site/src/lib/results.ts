/**
 * The single source of every number on the site: bend/bench/results/results.json,
 * imported at build time and checked against the shape the page understands.
 * A file that drifts from this shape fails the build with a readable message
 * instead of rendering a half-empty page.
 */
import raw from '../../../bend/bench/results/results.json';
import { z } from 'astro/zod';

const cell = z.union([z.string(), z.number().nonnegative(), z.null()]);

const table = z.object({
  unit: z.string().min(1),
  note: z.string().optional(),
  rows: z.array(z.record(z.string(), cell)).min(1),
});

const technique = z.object({
  adr: z.string().regex(/^\d{4}$/, 'ADR numbers are four digits, e.g. "0002"'),
  title: z.string().min(1),
  summary: z.string().min(1),
});

const schema = z.looseObject({
  machine: z.record(z.string(), z.string()),
  status_note: z.string().optional(),
  in_memory: table,
  cli: table,
  models: table.optional(),
  daemon: table.optional(),
  iroh: table.optional(),
  floors: z.array(z.string()).default([]),
  techniques: z.array(technique).default([]),
});

export type RawTable = z.infer<typeof table>;
export type Technique = z.infer<typeof technique>;
export type Results = z.infer<typeof schema>;

function load(): Results {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(
      `bend/bench/results/results.json does not match the shape the site expects:\n${z.prettifyError(parsed.error)}`,
    );
  }
  return parsed.data;
}

export const results: Results = load();
