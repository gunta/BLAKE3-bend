/**
 * What each measured implementation is made of, for the icons beside its name in
 * every chart and table: the language its hashing code is written in (or the
 * hand-written GPU kernel), where it runs, and on a GPU, the API. Read from the
 * series' own label and description in results.json, plus the machine it ran
 * on, so a new series gets its icons without an entry here.
 * Stack.astro draws a stack; this file only names its parts.
 */

/** A GPU API, which also names its vendor's GPUs: Metal is Apple's, CUDA NVIDIA's. */
export type GpuApi = 'metal' | 'cuda';

/** Written in. Metal and CUDA here are hand-written kernels in those languages. */
export type Engine = 'bend' | 'rust' | 'c' | 'go' | 'javascript' | 'webassembly' | GpuApi;

export type Part = Engine | 'cpu' | 'gpu';

export interface Stack {
  engine: Engine | undefined;
  cpu: boolean;
  gpu: boolean;
  /** The GPU API, when the engine has not already named it. */
  api: GpuApi | undefined;
}

export const PART_LABEL: Readonly<Record<Part, string>> = {
  bend: 'Bend',
  rust: 'Rust',
  c: 'C',
  go: 'Go',
  javascript: 'JavaScript',
  webassembly: 'WebAssembly',
  metal: 'Metal',
  cuda: 'CUDA',
  cpu: 'CPU',
  gpu: 'GPU',
};

/** The mark of the company whose GPUs an API drives, which stands for the API: Apple's for Metal, NVIDIA's for CUDA. */
export const VENDOR_MARK = { metal: 'apple', cuda: 'nvidia' } as const;

/** The GPU API a machine or label names: "Apple M5 Pro" and "Bend, Metal" are Metal; "NVIDIA B200" is CUDA. */
export function gpuApiOf(text: string): GpuApi | undefined {
  if (/\bCUDA\b|NVIDIA/i.test(text)) return 'cuda';
  if (/\bMetal\b|\bApple\b/i.test(text)) return 'metal';
  return undefined;
}

export interface Described {
  key: string;
  label: string;
  description?: string | undefined;
}

/** A hand-written GPU kernel rather than Bend's GPU path: "native Metal", "turboblake, native GPU kernel". */
const NATIVE_KERNEL = /\bnative (?:CUDA|Metal|GPU kernel)\b|\bhand-written (?:CUDA|Metal)\b/i;

/** The label first, then the machine: a description can name both ("the hand-written CUDA or Metal kernel"). */
function apiOf(s: Described, gpu: GpuApi | undefined): GpuApi | undefined {
  return gpuApiOf(s.label) ?? gpu ?? gpuApiOf(s.description ?? '');
}

function engineOf(s: Described, gpu: GpuApi | undefined): Engine | undefined {
  const text = `${s.label} ${s.description ?? ''}`;
  if (NATIVE_KERNEL.test(text)) return apiOf(s, gpu);
  if (/^bend(_|$)/.test(s.key)) return 'bend';
  if (/\bGo assembly\b|\bcrypto\/|golang\.org\//.test(text)) return 'go';
  // PyPI's blake3 is the Rust crate behind a Python module.
  if (/^(rust|b3sum|iroh|blake3|pypi)(_|$)/.test(s.key) || /\bRust\b|\bcrate\b|\brayon\b/.test(text)) return 'rust';
  if (/\bWebAssembly\b/.test(text)) return 'webassembly';
  if (/\bJavaScript\b/.test(text)) return 'javascript';
  // OpenSSL and CPython's hash modules are C, behind Python's hashlib and Node's crypto.
  if (/\bC\b|\bOpenSSL\b|\bhashlib\b|\bnode:crypto\b/.test(text)) return 'c';
  return undefined;
}

/** `gpu` is the API of the machine the series ran on, for labels like "Bend GPU" that do not say. */
export function stackOf(s: Described, gpu?: GpuApi): Stack {
  const engine = engineOf(s, gpu);
  const onGpu = /gpu|metal|cuda/i.test(s.key) || /\bGPU\b|\bMetal\b|\bCUDA\b/.test(s.label);
  const api = onGpu ? apiOf(s, gpu) : undefined;
  return { engine, cpu: !onGpu || /\bCPU\b/.test(s.label), gpu: onGpu, api: api === engine ? undefined : api };
}

/** The icons in reading order: written in, then CPU or GPU, then the GPU API. */
export function stackParts(s: Stack): Part[] {
  return [s.engine, s.cpu && ('cpu' as const), s.gpu && ('gpu' as const), s.api].filter((p): p is Part => !!p);
}

/** About how wide Stack.astro draws a stack, in em, gaps included: the Bend wordmark is two icons wide. */
export function stackEm(s: Stack): number {
  return stackParts(s).reduce((w, p) => w + (p === 'bend' ? 2.6 : 1.35), 0);
}

/** The stack in words, for its tooltip and screen readers: "Bend, on the GPU through Metal". */
export function stackText(s: Stack): string {
  const written = s.engine === 'metal' || s.engine === 'cuda' ? `Hand-written ${PART_LABEL[s.engine]}` : s.engine && PART_LABEL[s.engine];
  const where = [s.cpu && 'the CPU', s.gpu && 'the GPU'].filter(Boolean).join(' and ');
  const on = `on ${where}${s.api ? ` through ${PART_LABEL[s.api]}` : ''}`;
  return written ? `${written}, ${on}` : on.replace(/^on/, 'On');
}
