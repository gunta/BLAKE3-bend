/**
 * "From SHA-256 to the GPU": one 1 GiB buffer on the fastest GPU measured and on
 * the Mac, hashed by SHA-256, the official BLAKE3 on one core and on every core,
 * and turboblake on the CPU, on Bend's GPU path and on the native GPU kernel
 * (results.json `versus`, written by bend/bench/collect.py). The home page shows
 * it as bars, the benchmarks page as a table. No benchmark number is written in
 * this file.
 */
import { z } from 'astro/zod';
import { results } from './results';
import { fmtMeasured, fmtRate } from './format';
import { buildTable, gbPerSecond, parseBytes, type Table } from './model';

const kind = z.enum(['bend', 'blake3', 'other']);

const schema = z.looseObject({
  versus: z
    .object({
      title: z.string(),
      input: z.string(),
      unit: z.string(),
      note: z.string(),
      rows: z.array(z.record(z.string(), z.union([z.string(), z.number(), z.null()]))).min(1),
      machines: z.array(
        z.object({
          id: z.string(),
          title: z.string(),
          where: z.string(),
          api: z.string(),
          cores: z.number(),
          sha256: z.string(),
          gpu_memory: z.boolean(),
        }),
      ),
      series: z.record(z.string(), z.object({ label: z.string(), kind, description: z.string().optional() })),
    })
    .optional(),
});

export type VersusKind = z.infer<typeof kind>;

export interface VersusBar {
  key: string;
  label: string;
  kind: VersusKind;
  /** "on Bend's CUDA runtime": what this side was on this machine. */
  detail: string;
  ms: string;
  gbps: string;
  /** SHA-256's time over this one's: how many times faster than SHA-256. */
  timesSha: number;
  /** This bar's throughput as a share of the machine's fastest, for drawing to scale. */
  share: number;
  /** The fastest of the machine's sides. */
  best: boolean;
}

export interface VersusMachine {
  id: string;
  title: string;
  where: string;
  api: string;
  /** The GPU sides read from the GPU's own memory (NVIDIA), not memory shared with the CPU (Apple). */
  gpuMemory: boolean;
  bars: VersusBar[];
  fastest: VersusBar;
  sha: VersusBar;
  /** The official BLAKE3 on one core and on every core. */
  blake3: VersusBar | undefined;
  blake3All: VersusBar | undefined;
}

const parsed = schema.safeParse(results);
if (!parsed.success) {
  throw new Error(`bend/bench/results/results.json has no valid "versus" section (run bend/bench/collect.py):\n${z.prettifyError(parsed.error)}`);
}
const raw = parsed.data.versus;

/** What a series was on one machine: the GPU API, the core count, which SHA-256. */
function detail(key: string, m: NonNullable<typeof raw>['machines'][number]): string {
  switch (key) {
    case 'sha256':
      return `${m.sha256}, one core`;
    case 'blake3':
      return 'the official crate, one core';
    case 'blake3_all':
      return `the official crate, all ${m.cores} cores`;
    case 'bend_cpu':
      return `Bend's tree, all ${m.cores} cores`;
    case 'bend_gpu':
      return `Bend on ${m.api}`;
    case 'bend_native':
      return `hand-written ${m.api}`;
    default:
      return '';
  }
}

function machineOf(row: Record<string, string | number | null>, i: number): VersusMachine | undefined {
  const m = raw?.machines[i];
  const bytes = raw ? parseBytes(raw.input) : undefined;
  const sha = row.sha256;
  if (!raw || !m || bytes === undefined || typeof sha !== 'number') return undefined;
  const sides = Object.keys(raw.series).flatMap((key) => {
    const ms = row[key];
    return typeof ms === 'number' && ms > 0 ? [{ key, ms, rate: gbPerSecond(bytes, ms) }] : [];
  });
  const top = Math.max(...sides.map((s) => s.rate));
  const bars = sides.map(
    (s): VersusBar => ({
      key: s.key,
      label: raw.series[s.key]!.label,
      kind: raw.series[s.key]!.kind,
      detail: detail(s.key, m),
      ms: fmtMeasured(s.ms),
      gbps: fmtRate(s.rate),
      timesSha: sha / s.ms,
      share: s.rate / top,
      best: s.rate === top,
    }),
  );
  const fastest = bars.find((b) => b.best);
  const shaBar = bars.find((b) => b.key === 'sha256');
  if (!fastest || !shaBar) return undefined;
  return {
    id: m.id,
    title: m.title,
    where: m.where,
    api: m.api,
    gpuMemory: m.gpu_memory,
    bars,
    fastest,
    sha: shaBar,
    blake3: bars.find((b) => b.key === 'blake3'),
    blake3All: bars.find((b) => b.key === 'blake3_all'),
  };
}

/** "841×": how many times faster, whole numbers from 10 up. */
export function fmtTimes(x: number): string {
  return `${x >= 10 ? Math.round(x).toLocaleString('en-US') : x.toFixed(1)}×`;
}

export const versus = raw
  ? (() => {
      const machines = raw.rows.flatMap((r, i) => machineOf(r, i) ?? []);
      const lead = [...machines].sort((a, b) => b.fastest.timesSha - a.fastest.timesSha)[0];
      if (!lead) return undefined;
      const table: Table = buildTable(
        { unit: raw.unit, note: raw.note, rows: raw.rows.map((r) => ({ ...r, input: `${raw.input}, ${r.input}` })) },
        Object.fromEntries(
          Object.entries(raw.series).map(([k, s]) => [k, s.description === undefined ? { label: s.label } : { label: s.label, description: s.description }]),
        ),
      );
      return { title: raw.title, input: raw.input, note: raw.note, machines, lead, table };
    })()
  : undefined;
