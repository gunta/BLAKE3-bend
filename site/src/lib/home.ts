/**
 * The home page's numbers, picked from the same tables as the benchmarks page
 * (src/lib/page.ts) and the BLAKE3 team's chart (src/lib/official.ts). Each is
 * undefined when results.json lacks the table it comes from.
 */
import { fmtMeasured, fmtRate } from './format';
import { fmtSpeedup, gbPerSecond, parseBytes, splitInput } from './model';
import { OFFICIAL_SPEED } from './official';
import { cliTallies, headlines, machineName, sizeIn } from './page';
import { lawCount, universalCount } from './proofs';
import { withBase } from './site';

const x = (ratio: string) => ratio.replace(/x$/, '×');

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

/** In memory on the GPU: the biggest input, as throughput, on the machine the headline picked. */
export const gpu = (() => {
  const h = headlines.gpu;
  if (!h) return undefined;
  const c = h.comparison;
  const { size } = splitInput(c.row.label);
  const bytes = parseBytes(size);
  return {
    size,
    ms: fmtMeasured(c.bendValue),
    gbps: bytes ? fmtRate(gbPerSecond(bytes, c.bendValue)) : undefined,
    ratio: x(h.value),
    baselineLabel: c.baseline.label,
    // The context ends in "on the <machine>" when the GPU is not this one's.
    machine: / on (?:the )?(.+)$/.exec(h.context)?.[1] ?? machineName,
    // The GPU page has every GPU; an in-page anchor would point at the old home sections.
    href: h.href.startsWith('#') ? withBase('gpu/') : h.href,
  };
})();

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
