/**
 * Everything the landing page shows, derived from results.json in one place:
 * the tables with their series labels, the charts, the per-section tallies and
 * the hero's headline numbers. No benchmark number is written in this file.
 */
import { results } from './results';
import { gpuMachines } from './more';
import { withBase } from './site';
import { gpuApiOf } from './stack';
import { fmtList, fmtMeasured, fmtRange, fmtRate } from './format';
import {
  buildTable,
  compare,
  compareToFastest,
  fmtSpeedup,
  gbPerSecond,
  parseBytes,
  splitInput,
  tally,
  throughputCharts,
  timeChart,
  type Chart,
  type Comparison,
  type Series,
  type Table,
  type Tally,
} from './model';

export { results };

// ---------------------------------------------------------------- tables

/** Every table here was measured on the one machine results.json describes. */
const onMachine = { gpu: gpuApiOf(Object.values(results.machine).join(' ')) };

export const inMemory: Table = buildTable(results.in_memory, {
  rust: { label: 'Rust blake3', description: 'the official blake3 crate, NEON + rayon' },
  bend_cpu: { label: 'Bend CPU', description: 'Bend on the CPU cores (8-lane compress8)' },
  bend_gpu: { label: 'Bend GPU', description: 'Bend on the GPU (hash1!)' },
}, onMachine);

export const cli: Table = buildTable(results.cli, {
  b3sum: { label: 'b3sum', description: 'the official b3sum CLI' },
  bend: { label: 'turboblake', description: 'its Bend engine and loader, measured as bend/b3sum.bend' },
}, onMachine);

/** Real model weights, one shot: the case where most of the file is on disk. */
export const models: Table | undefined = results.models
  ? buildTable(results.models, {
      b3sum: { label: 'b3sum', description: 'the official b3sum CLI' },
      bend: { label: 'turboblake', description: 'its Bend engine and loader, streaming what is not cached' },
    }, onMachine)
  : undefined;

export const daemon: Table | undefined = results.daemon
  ? buildTable(results.daemon, {
      rust_seq: { label: 'Rust seq', description: 'one file at a time, like b3sum' },
      rust_par: { label: 'Rust par', description: 'rayon across files, the strongest baseline' },
      bend: { label: 'Bend', description: 'Bend, in a long-running process' },
      bend_cpu: { label: 'Bend CPU', description: 'Bend on the CPU cores, in a long-running process' },
      bend_gpu: { label: 'Bend GPU', description: 'Bend on the GPU, heap set up once' },
    }, onMachine)
  : undefined;

/** True while the iroh note says the Bend side computes the root hash only. */
export const irohHashOnly: boolean = /root hash only/i.test(results.iroh?.note ?? '');

export const iroh: Table | undefined = results.iroh
  ? buildTable(results.iroh, {
      iroh_mem_copy: { label: 'iroh mem, copy', description: 'in-memory store, data copied in' },
      iroh_fs_copy: { label: 'iroh fs, copy', description: 'file-system store, data copied in' },
      iroh_fs_ref: { label: 'iroh fs, ref', description: 'file-system store, file referenced in place' },
      bend: irohHashOnly
        ? { label: 'Bend, hash only', description: 'root hash only, no outboard yet' }
        : { label: 'Bend, hash + outboard', description: 'the same hash and bao outboard, in a long-running process' },
    }, onMachine)
  : undefined;

// ---------------------------------------------------------------- charts

export const inMemoryCharts: Chart[] = throughputCharts(inMemory, 'mem') ?? [timeChart(inMemory, 'mem')];
export const cliChart: Chart = timeChart(cli, 'cli');
export const modelsChart: Chart | undefined = models ? timeChart(models, 'models') : undefined;
export const daemonChart: Chart | undefined = daemon ? timeChart(daemon, 'daemon') : undefined;
export const irohChart: Chart | undefined = iroh ? timeChart(iroh, 'iroh') : undefined;

// ---------------------------------------------------------------- tallies

function tallies(table: Table, perBaseline: boolean): Tally[] {
  const out: Tally[] = [];
  for (const b of table.bend) {
    if (perBaseline && table.baselines.length > 1) {
      // Strongest baseline first: the one with the lowest total time.
      const total = (s: Series) => table.rows.reduce((sum, r) => sum + (r.values.get(s.key) ?? 0), 0);
      const ordered = [...table.baselines].sort((x, y) => total(x) - total(y));
      for (const base of ordered) {
        const t = tally(table, b, base);
        if (t) out.push(t);
      }
    } else {
      const t = tally(table, b, table.baselines.length === 1 ? table.baselines[0] : undefined);
      if (t) out.push(t);
    }
  }
  return out;
}

export const inMemoryTallies = tallies(inMemory, false);
export const cliTallies = tallies(cli, false);
export const modelsTallies = models ? tallies(models, false) : [];
export const daemonTallies = daemon ? tallies(daemon, true) : [];
export const irohTallies = iroh ? tallies(iroh, false) : [];

/** "level on all 7 workloads" style wording for the daemon race prose. */
export function levelWording(t: Tally | undefined): string | undefined {
  if (!t) return undefined;
  const n = t.all.length;
  if (t.tie.length === n) return `level on all ${n} workloads`;
  if (t.tie.length * 2 >= n) return `level on ${t.tie.length} of ${n} workloads`;
  return undefined;
}

// ---------------------------------------------------------------- headlines

export interface Headline {
  /** The figure itself: "2.40x", "up to 10.7x". */
  value: string;
  label: string;
  detail: string;
  href: string;
  comparison: Comparison;
  /** Short forms for the Open Graph card. */
  short: string;
  context: string;
}

const cpuSeries = inMemory.bend.find((s) => s.tone !== 'gpu');

function sized(table: Table) {
  return table.rows.map((row) => {
    const { size, mode } = splitInput(row.label);
    return { row, size, mode, bytes: parseBytes(size) };
  });
}

export interface GpuRun {
  /** The machine's section on the GPU page. */
  id: string;
  title: string;
  backend: string | undefined;
  /** Whose code ran: Bend's GPU path, or a hand-written kernel (bend/ref). */
  engine: 'Bend' | 'native';
  /** "a native CUDA kernel", "Bend's CUDA": what ran, for prose. */
  kernel: string;
  size: string;
  rate: number;
  /** The GPU run (as `bend`) against the official crate on the same machine's CPU (as `baseline`). */
  comparison: Comparison;
}

/** The largest input this Mac's GPU ran in memory: the size every GPU is compared at. */
const macGpuBytes = (() => {
  const s = inMemory.bend.find((b) => b.tone === 'gpu');
  const sizes = sized(inMemory).flatMap((r) => (s && r.bytes !== undefined && r.row.values.get(s.key) != null ? [r.bytes] : []));
  return sizes.length ? Math.max(...sizes) : undefined;
})();

/**
 * Every GPU run measured, Bend's and the hand-written kernels', on this Mac's
 * Metal and each NVIDIA card's CUDA, fastest first. Each runs the input size
 * this Mac's GPU ran (or its own largest, if it never ran that size), against
 * the official crate on all of the same machine's CPU cores: one size for every
 * GPU, and no peak size cherry-picked.
 */
export const gpuRuns: GpuRun[] = gpuMachines
  .flatMap((m): GpuRun[] => {
    const t = m.vsCpu;
    if (!t) return [];
    const kernels = t.series.filter((s) => s.tone === 'gpu' || m.nativeKeys.includes(s.key));
    const cpu = t.series.filter((s) => m.cpuBaselineKeys.includes(s.key));
    return kernels.flatMap((s): GpuRun[] => {
      const rows = sized(t).filter((r) => r.bytes !== undefined && r.row.values.get(s.key) != null);
      const top =
        rows.find((r) => r.bytes === macGpuBytes) ??
        rows.reduce<(typeof rows)[number] | undefined>((a, r) => (!a || (r.bytes ?? 0) >= (a.bytes ?? 0) ? r : a), undefined);
      if (!top || top.bytes === undefined) return [];
      // The strongest CPU baseline on that row.
      const c = cpu
        .map((base) => compare(top.row, s, base))
        .reduce<Comparison | undefined>((a, x) => (x && (!a || x.baselineValue < a.baselineValue) ? x : a), undefined);
      if (!c) return [];
      const engine = s.isBend ? 'Bend' : 'native';
      const api = m.backend ?? 'GPU';
      return [
        {
          id: m.id,
          title: m.title,
          backend: m.backend,
          engine,
          kernel: engine === 'Bend' ? `Bend's ${api}` : `a native ${api} kernel`,
          size: top.size,
          rate: gbPerSecond(top.bytes, c.bendValue),
          comparison: c,
        },
      ];
    });
  })
  .sort((a, b) => b.rate - a.rate);

function bestPerBackend(runs: GpuRun[]): GpuRun[] {
  return runs.filter((r, i) => runs.findIndex((o) => o.backend === r.backend) === i);
}

/** The fastest run on each GPU API, native kernels included: one for CUDA, one for Metal. */
export const gpuBest: GpuRun[] = bestPerBackend(gpuRuns);

/** The same for Bend's own GPU path only. */
export const bendGpuBest: GpuRun[] = bestPerBackend(gpuRuns.filter((r) => r.engine === 'Bend'));

/** "the official crate on all 16 CPU cores", from "Rust blake3, CPU (16 cores)". */
function cpuBaseline(c: Comparison): string {
  const cores = /(\d+)\s*cores/.exec(c.baseline.label)?.[1];
  return cores ? `the official crate on all ${cores} CPU cores` : c.baseline.label;
}

function gpuHeadline(): Headline | undefined {
  const best = gpuRuns[0];
  if (!best) return undefined;
  const c = best.comparison;
  const also = gpuBest
    .filter((r) => r !== best)
    .map((r) => ` With ${r.kernel} on the ${r.title}: ${fmtRate(r.rate)} GB/s on ${r.size}, ${fmtSpeedup(r.comparison).replace(/x$/, '×')} ${cpuBaseline(r.comparison)}.`)
    .join('');
  return {
    value: fmtSpeedup(c),
    label: `${c.bend.label} on the ${best.title} vs the official crate on its CPU, hashing ${best.size} in memory`,
    detail: `${fmtMeasured(c.bendValue)} ms with ${best.kernel}, against ${fmtMeasured(c.baselineValue)} ms for ${cpuBaseline(c)}, ${fmtRate(best.rate)} GB/s.${also}`,
    href: withBase(`gpu/#${best.id}`),
    comparison: c,
    short: `${c.bend.label} vs ${c.baseline.label}`,
    context: `${best.size} in memory on the ${best.title}`,
  };
}

function cliHeadline(): Headline | undefined {
  const t = cliTallies[0];
  if (!t) return undefined;
  const c = t.best;
  const n = t.all.length;
  const counts = [
    t.faster.length ? `faster on ${t.faster.length} of ${n} workloads` : '',
    t.tie.length ? `level on ${t.tie.length}` : '',
    t.slower.length ? `slower on ${t.slower.length}` : '',
  ].filter(Boolean);
  return {
    value: `${t.faster.length > 1 ? 'up to ' : ''}${fmtSpeedup(c)}`,
    label: `${t.bend.label} vs the official ${c.baseline.label}, one shot`,
    detail: `${c.row.label}: ${fmtMeasured(c.bendValue)} ms against ${fmtMeasured(c.baselineValue)} ms, process start included. ${capitalize(fmtList(counts))}.`,
    href: '#cli',
    comparison: c,
    short: `${t.bend.label} vs ${c.baseline.label}`,
    context: c.row.label,
  };
}

function modelsHeadline(): Headline | undefined {
  const t = modelsTallies[0];
  if (!t) return undefined;
  // The biggest file, not the best ratio: the first row is the headline file.
  const c = t.all[0];
  if (!c) return undefined;
  return {
    value: fmtSpeedup(c),
    label: `${t.bend.label} vs the official ${c.baseline.label} on real model weights`,
    detail: `${c.row.label}: ${fmtMeasured(c.bendValue)} s against ${fmtMeasured(c.baselineValue)} s, same hash.`,
    href: '#models',
    comparison: c,
    short: `${t.bend.label} vs ${c.baseline.label}`,
    context: c.row.label,
  };
}

function perCoreHeadline(): Headline | undefined {
  if (!cpuSeries) return undefined;
  const one = sized(inMemory).find((r) => /^(1|one|single)\b/i.test(r.mode));
  if (!one || one.bytes === undefined) return undefined;
  const c = compareToFastest(inMemory, one.row, cpuSeries);
  if (!c) return undefined;
  return {
    value: fmtSpeedup(c),
    label: `${cpuSeries.label} per core vs ${c.baseline.label}`,
    detail: `${one.size} in memory on ${one.mode}: ${fmtRate(gbPerSecond(one.bytes, c.bendValue))} GB/s against ${fmtRate(gbPerSecond(one.bytes, c.baselineValue))} GB/s.`,
    href: '#in-memory',
    comparison: c,
    short: `${cpuSeries.label} vs ${c.baseline.label}`,
    context: `${one.mode}, ${one.size} in memory`,
  };
}

export interface TieHeadline {
  lines: { text: string; href: string }[];
}

function tieHeadline(): TieHeadline | undefined {
  const lines: TieHeadline['lines'] = [];
  const strongest = daemonTallies[0];
  if (strongest && strongest.tie.length) {
    lines.push({
      text: `Kept running, start-up excluded, vs ${strongest.against}: ${fmtRange(Math.min(...strongest.tie.map((c) => c.ratio)), Math.max(...strongest.tie.map((c) => c.ratio)))} on ${strongest.tie.length} of ${strongest.all.length} workloads.`,
      href: '#daemon',
    });
  }
  const one = cliTallies[0];
  if (one && one.tie.length) {
    lines.push({
      text: `One-shot ${one.bend.label}: ${fmtList(one.tie.map((c) => c.row.label))}, ${fmtRange(Math.min(...one.tie.map((c) => c.ratio)), Math.max(...one.tie.map((c) => c.ratio)))}.`,
      href: '#cli',
    });
  }
  return lines.length ? { lines } : undefined;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const headlines = {
  models: modelsHeadline(),
  gpu: gpuHeadline(),
  cli: cliHeadline(),
  perCore: perCoreHeadline(),
  ties: tieHeadline(),
};

// ---------------------------------------------------------------- machine

const MACHINE_LABELS: Readonly<Record<string, string>> = {
  name: 'Machine',
  cpu: 'CPU',
  gpu: 'GPU',
  memory: 'Memory',
  os: 'OS',
  bend: 'Bend',
  reference: 'Reference',
};

export const machine: { label: string; value: string }[] = Object.entries(results.machine).map(([key, value]) => ({
  label: MACHINE_LABELS[key] ?? capitalize(key.replace(/_/g, ' ')),
  value,
}));

export const machineName: string = results.machine['name'] ?? 'the test machine';

// ---------------------------------------------------------------- floors

/** "Page faults on a mapped file: ~15 ms per GiB…" -> title + body. */
export const floors: { title: string; body: string | undefined }[] = results.floors.map((text) => {
  const i = text.indexOf(': ');
  if (i < 0) return { title: text, body: undefined };
  return { title: text.slice(0, i), body: capitalize(text.slice(i + 2)) };
});


// ---------------------------------------------------------------- outcomes

/** "DeepSeek-V4.1-Flash shard 48 (101.5 GB, bigger than RAM)" -> "101.5 GB". */
export function sizeIn(label: string): string | undefined {
  return /(\d+(?:\.\d+)?\s?(?:[KMGT]i?B))/.exec(label)?.[1];
}

/** The hero's proof line: the biggest real file, from the models table. */
export const heroProof = (() => {
  const c = headlines.models?.comparison;
  if (!c) return undefined;
  return {
    size: sizeIn(c.row.label),
    seconds: fmtMeasured(c.bendValue),
    baselineSeconds: fmtMeasured(c.baselineValue),
    ratio: fmtSpeedup(c),
    baseline: c.baseline.label,
  };
})();
