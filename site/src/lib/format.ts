/** Number formatting shared by charts, tables and the hero. */

const measured = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 });

/** A measured value exactly as results.json states it (no invented precision). */
export function fmtMeasured(value: number): string {
  return measured.format(value);
}

/** Derived throughput: three significant figures, no exponent notation. */
export function fmtRate(value: number): string {
  if (value >= 100) return value.toFixed(0);
  return value.toPrecision(3);
}

/** Derived speedup factor, without the trailing "x". */
export function fmtRatio(ratio: number): string {
  return ratio >= 10 ? ratio.toFixed(1) : ratio.toFixed(2);
}

/** Speedup factor with its "x": 2.40x, 10.7x. */
export function fmtX(ratio: number): string {
  return `${fmtRatio(ratio)}x`;
}

/** "0.96x to 1.03x", or a single value when both ends agree. */
export function fmtRange(min: number, max: number): string {
  const lo = fmtX(min);
  const hi = fmtX(max);
  return lo === hi ? lo : `${lo} to ${hi}`;
}

/** Axis tick label: compact, no trailing zeros. */
export function fmtTick(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2, notation: value >= 10_000 ? 'compact' : 'standard' }).format(value);
}

/** "a, b and c" */
export function fmtList(items: readonly string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** Plural helper: count + noun, with an explicit plural form when it is irregular. */
export function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${count} ${count === 1 ? noun : many}`;
}

/** URL-safe id from a free-text label. */
export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
