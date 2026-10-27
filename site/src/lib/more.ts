/**
 * The GPU, languages and install pages' data: the sections of results.json that
 * bend/bench/collect.py writes (gpu_metal, gpu_nvidia, languages,
 * deepseek_linux), checked here and turned into the same tables and charts as
 * the home page's. No benchmark number is written in this file.
 */
import { z } from 'astro/zod';
import { results } from './results';
import { buildTable, throughputCharts, timeChart, type Chart, type Table } from './model';
import { gpuApiOf } from './stack';

const kind = z.enum(['bend', 'blake3', 'other']);

const table = z.object({
  title: z.string(),
  machine: z.string(),
  unit: z.string(),
  note: z.string().optional(),
  rows: z.array(z.record(z.string(), z.union([z.string(), z.number(), z.null()]))).min(1),
  series: z.record(z.string(), z.object({ label: z.string(), kind, description: z.string().optional() })),
});

const schema = z.looseObject({
  gpu_metal: table,
  gpu_nvidia: z.array(table).default([]),
  deepseek_linux: table.optional(),
  languages: z.record(z.string(), table).default({}),
});

export type Kind = z.infer<typeof kind>;
type RawMore = z.infer<typeof table>;

function load() {
  const parsed = schema.safeParse(results);
  if (!parsed.success) {
    throw new Error(
      `bend/bench/results/results.json has no valid GPU/language sections (run bend/bench/collect.py):\n${z.prettifyError(parsed.error)}`,
    );
  }
  return parsed.data;
}

const more = load();

/** A table of some of a raw table's series, labelled from its series map. */
function pick(raw: RawMore, keys: readonly string[]): Table {
  const rows = raw.rows.map((r) => Object.fromEntries(Object.entries(r).filter(([k]) => k === 'input' || keys.includes(k))));
  const meta = Object.fromEntries(
    keys.flatMap((k) => {
      const s = raw.series[k];
      return s ? [[k, s.description === undefined ? { label: s.label } : { label: s.label, description: s.description }] as const] : [];
    }),
  );
  return buildTable({ unit: raw.unit, note: raw.note, rows }, meta, { gpu: gpuApiOf(`${raw.title} ${raw.machine}`) });
}

/** Speedups against the BLAKE3 alternatives only; other hashes are shown for scale. */
function againstBlake3(t: Table, raw: RawMore): Table {
  return { ...t, baselines: t.baselines.filter((s) => raw.series[s.key]?.kind === 'blake3') };
}

const charts = (t: Table, id: string): Chart[] => throughputCharts(t, id) ?? [timeChart(t, id)];

// ---------------------------------------------------------------- GPU

export interface GpuMachine {
  id: string;
  title: string;
  machine: string;
  note: string | undefined;
  gpu: Table;
  gpuCharts: Chart[];
  cpu: Table | undefined;
  cpuCharts: Chart[];
  /** The GPU API Bend compiled to ("Metal", "CUDA"), from its series label ("Bend, CUDA"). */
  backend: string | undefined;
  /** Bend and the native kernels on the GPU, with the CPU baselines of the same machine (the official crate on every core). */
  vsCpu: Table | undefined;
  /** The hand-written kernels' series (native_cuda, metal); the runs in Bend's leaf shape are diagnostics and left out. */
  nativeKeys: string[];
  cpuBaselineKeys: string[];
}

function gpuMachine(raw: RawMore, id: string): GpuMachine {
  const keys = Object.keys(raw.series);
  const isGpu = (k: string) => /gpu|metal|cuda/.test(k);
  const gpu = pick(raw, keys.filter(isGpu));
  const cpuKeys = keys.filter((k) => !isGpu(k));
  const cpu = cpuKeys.some((k) => k.startsWith('bend')) && cpuKeys.some((k) => !k.startsWith('bend')) ? pick(raw, cpuKeys) : undefined;
  const bendGpu = keys.filter((k) => isGpu(k) && k.startsWith('bend'));
  const nativeKeys = keys.filter((k) => isGpu(k) && !/bend/.test(k));
  const cpuBaselines = cpuKeys.filter((k) => !k.startsWith('bend'));
  return {
    id,
    title: raw.title,
    machine: raw.machine,
    note: raw.note,
    gpu,
    gpuCharts: charts(gpu, `${id}-gpu`),
    cpu,
    cpuCharts: cpu ? charts(cpu, `${id}-cpu`) : [],
    backend: /\b(Metal|CUDA)\b/i.exec(raw.series[bendGpu[0] ?? '']?.label ?? '')?.[1],
    vsCpu: bendGpu.length && cpuBaselines.length ? pick(raw, [...bendGpu, ...nativeKeys, ...cpuBaselines]) : undefined,
    nativeKeys,
    cpuBaselineKeys: cpuBaselines,
  };
}

export const gpuMachines: GpuMachine[] = [
  gpuMachine(more.gpu_metal, 'metal'),
  ...more.gpu_nvidia.map((t) => gpuMachine(t, t.title.toLowerCase().replace(/[^a-z0-9]+/g, '-'))),
];

/** Native time ÷ Bend time on each GPU's biggest row: how much of native speed Bend reaches. */
export const gpuShares = gpuMachines.map((m) => {
  const row = m.gpu.rows[m.gpu.rows.length - 1]!;
  const bend = row.values.get('bend_gpu');
  const native = Math.min(...m.gpu.baselines.map((s) => row.values.get(s.key) ?? Infinity));
  return { title: m.title, input: row.label, share: bend && Number.isFinite(native) ? native / bend : undefined };
});

// ---------------------------------------------------------------- languages

export interface Language {
  id: string;
  title: string;
  machine: string;
  note: string | undefined;
  table: Table;
  charts: Chart[];
  /** Series keys of other hash functions (the toggles), with their labels. */
  others: { key: string; label: string }[];
}

const ORDER = ['c', 'rust', 'python', 'node', 'bun', 'go', 'go_linux'];

export const languages: Language[] = Object.entries(more.languages)
  .sort(([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99))
  .map(([id, raw]) => {
    const keys = Object.keys(raw.series);
    const table = againstBlake3(pick(raw, keys), raw);
    return {
      id,
      title: raw.title,
      machine: raw.machine,
      note: raw.note,
      table,
      charts: charts(table, `lang-${id}`),
      others: keys.filter((k) => raw.series[k]?.kind === 'other').map((k) => ({ key: k, label: raw.series[k]!.label })),
    };
  });

/** Every other hash any language measured, in a fixed order, for one set of toggles. */
export const otherHashes: { key: string; label: string }[] = (() => {
  const seen = new Map<string, string>();
  for (const l of languages) for (const o of l.others) if (!seen.has(o.key)) seen.set(o.key, o.label);
  const order = ['sha256', 'sha512', 'sha1', 'md5', 'blake2b', 'blake2s', 'sha3_256'];
  return [...seen].sort(([a], [b]) => order.indexOf(a) - order.indexOf(b)).map(([key, label]) => ({ key, label }));
})();

// ---------------------------------------------------------------- DeepSeek on Linux

export const deepseekLinux = more.deepseek_linux
  ? (() => {
      const raw = more.deepseek_linux;
      const t = pick(raw, Object.keys(raw.series));
      return { title: raw.title, machine: raw.machine, note: raw.note, table: t, chart: timeChart(t, 'deepseek-linux') };
    })()
  : undefined;
