/**
 * Everything the landing page shows, derived from results.json in one place:
 * the tables with their series labels, the charts, the per-section tallies and
 * the hero's headline numbers. No benchmark number is written in this file.
 */
import { results } from './results';
import { fmtList, fmtMeasured, fmtRange, fmtRate } from './format';
import {
  buildTable,
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

export const inMemory: Table = buildTable(results.in_memory, {
  rust: { label: 'Rust blake3', description: 'the official blake3 crate, NEON + rayon' },
  bend_cpu: { label: 'Bend CPU', description: 'Bend on the CPU cores (8-lane compress8)' },
  bend_gpu: { label: 'Bend GPU', description: 'Bend on the GPU (hash1!)' },
});

export const cli: Table = buildTable(results.cli, {
  b3sum: { label: 'b3sum', description: 'the official b3sum CLI' },
  bend: { label: 'Bend b3sum', description: 'bend/b3sum.bend, CPU only' },
});

/** Real model weights, one shot: the case where most of the file is on disk. */
export const models: Table | undefined = results.models
  ? buildTable(results.models, {
      b3sum: { label: 'b3sum', description: 'the official b3sum CLI' },
      bend: { label: 'Bend b3sum', description: 'bend/b3sum.bend, streaming what is not cached' },
    })
  : undefined;

export const daemon: Table | undefined = results.daemon
  ? buildTable(results.daemon, {
      rust_seq: { label: 'Rust seq', description: 'one file at a time, like b3sum' },
      rust_par: { label: 'Rust par', description: 'rayon across files, the strongest baseline' },
      bend: { label: 'Bend', description: 'Bend, in a long-running process' },
      bend_cpu: { label: 'Bend CPU', description: 'Bend on the CPU cores, in a long-running process' },
      bend_gpu: { label: 'Bend GPU', description: 'Bend on the GPU, heap set up once' },
    })
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
    })
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

const gpuSeries = inMemory.bend.find((s) => s.tone === 'gpu');
const cpuSeries = inMemory.bend.find((s) => s.tone !== 'gpu');

function sized(table: Table) {
  return table.rows.map((row) => {
    const { size, mode } = splitInput(row.label);
    return { row, size, mode, bytes: parseBytes(size) };
  });
}

function gpuHeadline(): Headline | undefined {
  if (!gpuSeries) return undefined;
  const rows = sized(inMemory).filter((r) => r.bytes !== undefined && r.row.values.get(gpuSeries.key) != null);
  // The largest input the GPU ran: the headline does not cherry-pick the peak.
  const top = rows.reduce<(typeof rows)[number] | undefined>((a, r) => (!a || (r.bytes ?? 0) >= (a.bytes ?? 0) ? r : a), undefined);
  if (!top || top.bytes === undefined) return undefined;
  const c = compareToFastest(inMemory, top.row, gpuSeries);
  if (!c) return undefined;
  const rate = gbPerSecond(top.bytes, c.bendValue);
  const peak = rows.reduce<{ rate: number; size: string } | undefined>((a, r) => {
    const ms = r.row.values.get(gpuSeries.key);
    if (ms == null || r.bytes === undefined) return a;
    const v = gbPerSecond(r.bytes, ms);
    return !a || v > a.rate ? { rate: v, size: r.size } : a;
  }, undefined);
  const peakText = peak && peak.size !== top.size ? ` It peaks at ${fmtRate(peak.rate)} GB/s on ${peak.size}.` : '';
  return {
    value: fmtSpeedup(c),
    label: `${gpuSeries.label} vs the official ${c.baseline.label} crate, hashing ${top.size} in memory`,
    detail: `${fmtMeasured(c.bendValue)} ms against ${fmtMeasured(c.baselineValue)} ms${top.mode ? ` on ${top.mode}` : ''}, ${fmtRate(rate)} GB/s.${peakText}`,
    href: '#in-memory',
    comparison: c,
    short: `${gpuSeries.label} vs ${c.baseline.label}`,
    context: `${top.size} in memory`,
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

