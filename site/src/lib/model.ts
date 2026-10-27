/**
 * Turns the raw result tables into what the page draws: typed series, rows,
 * speedups with an honest win / tie / loss verdict, chart models and table views.
 *
 * Everything here is generic over the columns of results.json: a column whose key
 * starts with `bend` is a Bend measurement, every other numeric column is a
 * baseline. New rows and new columns show up on the page without code changes.
 */
import type { RawTable } from './results';
import { fmtMeasured, fmtRate, fmtRatio, fmtX, slug } from './format';
import { stackOf, type GpuApi, type Stack } from './stack';

/** Within this band either way (5%), a result is called a tie. */
export const TIE_BAND = 0.05;
/** The band as text for the page: "5%". */
export const TIE_TEXT = `${Math.round(TIE_BAND * 100)}%`;
const EPS = 1e-9;

export type Verdict = 'faster' | 'tie' | 'slower';
export type Tone = 'bend' | 'bend-alt' | 'gpu' | 'base-1' | 'base-2' | 'base-3';

export const VERDICT: Readonly<Record<Verdict, { icon: string; word: string }>> = {
  faster: { icon: '▲', word: 'faster' },
  tie: { icon: '=', word: 'tie' },
  slower: { icon: '▼', word: 'slower' },
};

export interface SeriesMeta {
  label: string;
  description?: string;
}

export interface Series {
  key: string;
  label: string;
  description: string | undefined;
  isBend: boolean;
  tone: Tone;
  /** Written in, CPU or GPU, and the GPU API: the icons beside its name. */
  stack: Stack;
}

export interface Row {
  id: string;
  label: string;
  values: ReadonlyMap<string, number | null>;
}

export interface Table {
  /** Unit as results.json states it, e.g. "ms per round". */
  unit: string;
  /** Short unit for value labels, e.g. "ms". */
  valueUnit: string;
  note: string | undefined;
  /** Header for the row-label column, e.g. "Workload". */
  rowHeader: string;
  series: Series[];
  bend: Series[];
  baselines: Series[];
  rows: Row[];
}

export interface Comparison {
  row: Row;
  bend: Series;
  baseline: Series;
  bendValue: number;
  baselineValue: number;
  /** Baseline time / Bend time: above 1 means Bend is faster. */
  ratio: number;
  verdict: Verdict;
}

function humanize(key: string): string {
  const text = key.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** `gpu`: the API of the machine the table was measured on, for series that run on its GPU. */
export function buildTable(raw: RawTable, meta: Readonly<Record<string, SeriesMeta>> = {}, opts: { gpu?: GpuApi | undefined } = {}): Table {
  const first = raw.rows[0];
  if (!first) throw new Error('results.json: a table has no rows');
  const labelKey = Object.keys(first).find((k) => typeof first[k] === 'string');
  if (!labelKey) throw new Error('results.json: a table row has no text label (such as "workload")');

  const keys: string[] = [];
  for (const row of raw.rows) {
    for (const [key, value] of Object.entries(row)) {
      if (key === labelKey) continue;
      if (typeof value === 'string') {
        throw new Error(`results.json: "${key}" holds text ("${value}") where a number or null was expected`);
      }
      if (!keys.includes(key)) keys.push(key);
    }
  }

  const baseTones = ['base-1', 'base-2', 'base-3'] as const;
  let baseCount = 0;
  let bendCount = 0;
  const series: Series[] = keys.map((key) => {
    const isBend = /^bend(_|$)/.test(key);
    let tone: Tone;
    if (isBend) {
      tone = /gpu/.test(key) ? 'gpu' : bendCount++ === 0 ? 'bend' : 'bend-alt';
    } else {
      tone = baseTones[Math.min(baseCount++, baseTones.length - 1)] ?? 'base-1';
    }
    const m = meta[key];
    const label = m?.label ?? humanize(key);
    return { key, label, description: m?.description, isBend, tone, stack: stackOf({ key, label, description: m?.description }, opts.gpu) };
  });

  const bend = series.filter((s) => s.isBend);
  const baselines = series.filter((s) => !s.isBend);
  if (bend.length === 0 || baselines.length === 0) {
    throw new Error(`results.json: a table needs a "bend…" column and a baseline column (found: ${keys.join(', ')})`);
  }

  const rows: Row[] = raw.rows.map((r) => {
    const label = r[labelKey];
    if (typeof label !== 'string') throw new Error(`results.json: a row is missing its "${labelKey}" label`);
    const values = new Map<string, number | null>();
    for (const s of series) {
      const v = r[s.key];
      values.set(s.key, typeof v === 'number' ? v : null);
    }
    return { id: slug(label), label, values };
  });

  return {
    unit: raw.unit,
    valueUnit: raw.unit.split(/\s+/)[0] ?? raw.unit,
    note: raw.note,
    rowHeader: humanize(labelKey),
    series,
    bend,
    baselines,
    rows,
  };
}

export function verdictOf(ratio: number): Verdict {
  if (ratio >= 1 + TIE_BAND - EPS) return 'faster';
  if (ratio <= 1 / (1 + TIE_BAND) + EPS) return 'slower';
  return 'tie';
}

/**
 * Speedup as shown on the page. Two decimals, except for a tie that would
 * round onto the 5% line (1.045 -> "1.05x"): that one gets a third decimal,
 * so a tie never displays a value that reads as a win or a loss.
 */
export function fmtSpeedup(c: Pick<Comparison, 'ratio' | 'verdict'>): string {
  if (c.verdict === 'tie' && Math.abs(Number(fmtRatio(c.ratio)) - 1) >= TIE_BAND - EPS) {
    return `${c.ratio.toFixed(3)}x`;
  }
  return fmtX(c.ratio);
}

export function compare(row: Row, bend: Series, baseline: Series): Comparison | undefined {
  const b = row.values.get(bend.key);
  const r = row.values.get(baseline.key);
  if (b == null || r == null || b <= 0 || r <= 0) return undefined;
  const ratio = r / b;
  return { row, bend, baseline, bendValue: b, baselineValue: r, ratio, verdict: verdictOf(ratio) };
}

/** The fastest baseline measured in this row: the strongest comparison available. */
export function fastestBaseline(table: Table, row: Row): Series | undefined {
  let best: Series | undefined;
  let bestValue = Number.POSITIVE_INFINITY;
  for (const s of table.baselines) {
    const v = row.values.get(s.key);
    if (v != null && v > 0 && v < bestValue) {
      best = s;
      bestValue = v;
    }
  }
  return best;
}

export function compareToFastest(table: Table, row: Row, bend: Series): Comparison | undefined {
  const baseline = fastestBaseline(table, row);
  return baseline ? compare(row, bend, baseline) : undefined;
}

export interface Tally {
  bend: Series;
  /** Who Bend is compared with: a baseline's label, or "the fastest baseline". */
  against: string;
  all: Comparison[];
  faster: Comparison[];
  tie: Comparison[];
  slower: Comparison[];
  min: number;
  max: number;
  best: Comparison;
}

export function tally(table: Table, bend: Series, baseline?: Series): Tally | undefined {
  const all: Comparison[] = [];
  for (const row of table.rows) {
    const c = baseline ? compare(row, bend, baseline) : compareToFastest(table, row, bend);
    if (c) all.push(c);
  }
  const best = all.reduce<Comparison | undefined>((a, c) => (!a || c.ratio > a.ratio ? c : a), undefined);
  if (!best) return undefined;
  const ratios = all.map((c) => c.ratio);
  return {
    bend,
    against: baseline ? baseline.label : 'the fastest baseline',
    all,
    faster: all.filter((c) => c.verdict === 'faster'),
    tie: all.filter((c) => c.verdict === 'tie'),
    slower: all.filter((c) => c.verdict === 'slower'),
    min: Math.min(...ratios),
    max: Math.max(...ratios),
    best,
  };
}

// ---------------------------------------------------------------- sizes

const UNIT_BYTES: Readonly<Record<string, number>> = {
  B: 1,
  KiB: 2 ** 10,
  MiB: 2 ** 20,
  GiB: 2 ** 30,
  TiB: 2 ** 40,
  KB: 1e3,
  MB: 1e6,
  GB: 1e9,
  TB: 1e12,
};

/** "256 MiB" -> 268435456. The whole string must be one size. */
export function parseBytes(text: string): number | undefined {
  const m = /^\s*(\d+(?:\.\d+)?)\s*(TiB|GiB|MiB|KiB|TB|GB|MB|KB|B)\s*$/.exec(text);
  if (!m || !m[1] || !m[2]) return undefined;
  const unit = UNIT_BYTES[m[2]];
  return unit === undefined ? undefined : Number(m[1]) * unit;
}

/** "1 GiB, all cores" -> { size: "1 GiB", mode: "all cores" } */
export function splitInput(label: string): { size: string; mode: string } {
  const i = label.indexOf(',');
  if (i < 0) return { size: label.trim(), mode: '' };
  return { size: label.slice(0, i).trim(), mode: label.slice(i + 1).trim() };
}

/** Throughput in GB/s (decimal gigabytes per second) from bytes and milliseconds. */
export function gbPerSecond(bytes: number, ms: number): number {
  return bytes / (ms * 1e6);
}

// ---------------------------------------------------------------- charts

export interface Axis {
  max: number;
  ticks: number[];
}

export function niceAxis(max: number, target = 5): Axis {
  if (!(max > 0)) return { max: 1, ticks: [0, 1] };
  const raw = max / target;
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  const top = Math.ceil(max / step - EPS) * step;
  const ticks: number[] = [];
  for (let i = 0; i * step <= top + step * EPS; i++) ticks.push(Number((i * step).toPrecision(12)));
  return { max: Number(top.toPrecision(12)), ticks };
}

export interface ChartBar {
  series: Series;
  value: number | null;
  /** value / axis max, 0..1 */
  fraction: number;
  /** Visible value label, e.g. "27.8 ms". */
  text: string;
  /** Extra words for screen readers, e.g. the time behind a throughput. */
  detail: string | undefined;
  comparison: Comparison | undefined;
}

export interface ChartGroup {
  id: string;
  label: string;
  bars: ChartBar[];
}

export interface Chart {
  id: string;
  title: string | undefined;
  quantity: 'time' | 'throughput';
  better: 'lower' | 'higher';
  /** e.g. "ms per round" or "GB/s" */
  axisUnit: string;
  series: Series[];
  groups: ChartGroup[];
  axis: Axis;
}

function presentSeries(table: Table, rows: readonly Row[]): Series[] {
  return table.series.filter((s) => rows.some((r) => r.values.get(s.key) != null));
}

/** One chart of times, every row a group, one shared axis. Lower is better. */
export function timeChart(table: Table, id: string, title?: string): Chart {
  const series = presentSeries(table, table.rows);
  const max = Math.max(...table.rows.flatMap((r) => series.map((s) => r.values.get(s.key) ?? 0)));
  const axis = niceAxis(max);
  const groups: ChartGroup[] = table.rows.map((row) => ({
    id: `${id}-${row.id}`,
    label: row.label,
    bars: series.map((s): ChartBar => {
      const v = row.values.get(s.key) ?? null;
      return {
        series: s,
        value: v,
        fraction: v == null ? 0 : v / axis.max,
        text: v == null ? 'not measured' : `${fmtMeasured(v)} ${table.valueUnit}`,
        detail: undefined,
        comparison: s.isBend ? compareToFastest(table, row, s) : undefined,
      };
    }),
  }));
  return { id, title, quantity: 'time', better: 'lower', axisUnit: table.unit, series, groups, axis };
}

/**
 * Throughput charts (GB/s, higher is better) for tables whose row labels are
 * sizes, such as "1 GiB, all cores". Rows split into one chart per mode
 * ("all cores", "1 core") so each chart has a fair shared axis. Returns
 * undefined when a label is not a size, and the caller falls back to times.
 */
export function throughputCharts(table: Table, id: string): Chart[] | undefined {
  const parsed = table.rows.map((row) => {
    const { size, mode } = splitInput(row.label);
    return { row, size, mode, bytes: parseBytes(size) };
  });
  if (table.valueUnit !== 'ms' || parsed.some((p) => p.bytes === undefined)) return undefined;

  const modes: string[] = [];
  for (const p of parsed) if (!modes.includes(p.mode)) modes.push(p.mode);
  // Widest comparison first: "all cores" before "1 core".
  modes.sort((a, b) => Number(/^1\b|one|single/i.test(a)) - Number(/^1\b|one|single/i.test(b)));

  return modes.map((mode): Chart => {
    const items = parsed.filter((p) => p.mode === mode);
    const rows = items.map((p) => p.row);
    const series = presentSeries(table, rows);
    const rate = (p: (typeof items)[number], s: Series): number | null => {
      const ms = p.row.values.get(s.key);
      return ms == null || ms <= 0 || p.bytes === undefined ? null : gbPerSecond(p.bytes, ms);
    };
    const max = Math.max(...items.flatMap((p) => series.map((s) => rate(p, s) ?? 0)));
    const axis = niceAxis(max);
    const chartId = `${id}-${slug(mode || 'all')}`;
    return {
      id: chartId,
      title: mode ? mode.charAt(0).toUpperCase() + mode.slice(1) : undefined,
      quantity: 'throughput',
      better: 'higher',
      axisUnit: 'GB/s',
      series,
      axis,
      groups: items.map((p) => ({
        id: `${chartId}-${p.row.id}`,
        label: p.size,
        bars: series.map((s): ChartBar => {
          const v = rate(p, s);
          const ms = p.row.values.get(s.key);
          return {
            series: s,
            value: v,
            fraction: v == null ? 0 : v / axis.max,
            text: v == null ? 'not measured' : `${fmtRate(v)} GB/s`,
            detail: ms == null ? undefined : `${fmtMeasured(ms)} ms`,
            comparison: s.isBend ? compareToFastest(table, p.row, s) : undefined,
          };
        }),
      })),
    };
  });
}

// ---------------------------------------------------------------- tables

export interface TableCell {
  text: string;
  sub: string | undefined;
  verdict: Verdict | undefined;
}

export interface TableView {
  caption: string;
  /** A measurement column carries its series' stack, for the icons in its header. */
  head: { text: string; stack?: Stack }[];
  rows: { header: string; cells: TableCell[] }[];
}

/**
 * Every measurement, plus every Bend-vs-baseline speedup, in one table.
 * With `throughput`, row labels that are sizes also get GB/s under each time.
 */
export function tableView(table: Table, caption: string, opts: { throughput?: boolean } = {}): TableView {
  const pairs = table.bend.flatMap((b) => table.baselines.map((base) => ({ b, base })));
  const head = [
    { text: table.rowHeader },
    ...table.series.map((s) => ({ text: `${s.label} (${table.valueUnit})`, stack: s.stack })),
    ...pairs.map(({ b, base }) => ({ text: `${b.label} vs ${base.label}` })),
  ];
  const rows = table.rows.map((row) => {
    const bytes = opts.throughput ? parseBytes(splitInput(row.label).size) : undefined;
    const values: TableCell[] = table.series.map((s) => {
      const v = row.values.get(s.key);
      if (v == null) return { text: 'not measured', sub: undefined, verdict: undefined };
      return {
        text: fmtMeasured(v),
        sub: bytes !== undefined && v > 0 ? `${fmtRate(gbPerSecond(bytes, v))} GB/s` : undefined,
        verdict: undefined,
      };
    });
    const ratios: TableCell[] = pairs.map(({ b, base }) => {
      const c = compare(row, b, base);
      if (!c) return { text: 'n/a', sub: undefined, verdict: undefined };
      return { text: fmtSpeedup(c), sub: VERDICT[c.verdict].word, verdict: c.verdict };
    });
    return { header: row.label, cells: [...values, ...ratios] };
  });
  return { caption, head, rows };
}
