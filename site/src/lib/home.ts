/**
 * The home page's numbers, picked from the same tables as the benchmarks page
 * (src/lib/page.ts) and the BLAKE3 team's chart (src/lib/official.ts). Each is
 * undefined when results.json lacks the table it comes from.
 */
import { fmtMeasured, fmtRate } from './format';
import { fmtSpeedup } from './model';
import { OFFICIAL_SPEED } from './official';
import { cliTallies, gpuBest, gpuRuns, headlines, machineName, sizeIn } from './page';
import { lawCount, universalCount } from './proofs';

const x = (ratio: string) => ratio.replace(/x$/, '×');
/** A rate with thousands grouped: "1,674". */
const grouped = (rate: number) => Number(fmtRate(rate)).toLocaleString('en-US', { maximumFractionDigits: 2 });

/** The biggest real file: a model shard bigger than RAM. */
export const model = (() => {
  const c = headlines.models?.comparison;
  if (!c) return undefined;
  return {
    size: sizeIn(c.row.label) ?? 'A huge',
    deepseek: /deepseek/i.test(c.row.label),
    seconds: fmtMeasured(c.bendValue),
    baselineSeconds: fmtMeasured(c.baselineValue),
    ratio: x(fmtSpeedup(c)),
    bend: c.bendValue,
    baseline: c.baselineValue,
    baselineLabel: c.baseline.label,
  };
})();

/** Many small files: the command line's best workload. */
export const folders = (() => {
  const c = cliTallies[0]?.best;
  if (!c) return undefined;
  const m = /^([\d,]+)\s*x\s*(.+)$/.exec(c.row.label);
  return {
    files: m ? `${m[1]} files of ${m[2]}` : c.row.label,
    ms: fmtMeasured(c.bendValue),
    baselineMs: fmtMeasured(c.baselineValue),
    ratio: x(fmtSpeedup(c)),
    baselineLabel: c.baseline.label,
  };
})();

/** In memory on the GPU: the fastest run measured (native kernels included), on its biggest input. */
export const gpu = (() => {
  const h = headlines.gpu;
  const run = gpuRuns[0];
  if (!h || !run) return undefined;
  const c = h.comparison;
  // Past 1,000 GB/s the figure reads (and fits the tile) better in TB/s.
  const tera = run.rate >= 1000;
  return {
    size: run.size,
    ms: fmtMeasured(c.bendValue),
    rate: tera ? (run.rate / 1000).toPrecision(3) : fmtRate(run.rate),
    unit: tera ? 'TB/s' : 'GB/s',
    ratio: x(h.value),
    baselineLabel: c.baseline.label,
    machine: run.title,
    kernel: run.kernel,
    href: h.href,
  };
})();

/** The fastest run on each GPU API (CUDA, Metal), fastest first, with its share of the fastest for the tile's bars. */
export const gpuApis = gpuBest.map((r) => ({
  backend: r.backend ?? 'GPU',
  engine: r.engine,
  machine: r.title,
  gbps: grouped(r.rate),
  share: r.rate / (gpuBest[0]?.rate ?? r.rate),
}));

/** The machine every CPU figure was measured on. */
export const machine = machineName;

/** BLAKE3 against SHA-256 on one core, in the BLAKE3 team's own benchmark. */
export const official = (() => {
  const bars = OFFICIAL_SPEED.bars;
  const of = (name: string) => bars.find((b) => b.name === name)?.value ?? 0;
  const pick = ['BLAKE3', 'SHA-1', 'MD5', 'SHA-256'].map((name) => ({ name, value: of(name) }));
  return {
    times: Math.round(of('BLAKE3') / Math.max(1, of('SHA-256'))),
    bars: pick,
    max: Math.max(...pick.map((b) => b.value)),
    source: OFFICIAL_SPEED.source,
    setup: OFFICIAL_SPEED.setup,
  };
})();

export const laws = lawCount;
/** Of those, the laws that hold for every input or every size (the rest are computed). */
export const universalLaws = universalCount;
