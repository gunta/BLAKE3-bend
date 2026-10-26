/**
 * One vgpu context for every canvas on the page, and the rules they share:
 * draw only while on screen and while the tab is visible, keep one still frame
 * for people who ask for reduced motion, and give up quietly (null) where
 * WebGPU is missing so the page falls back to its static art.
 */
import { init, type Gpu } from 'vgpu';

let pending: Promise<Gpu | null> | undefined;

export function getGpu(): Promise<Gpu | null> {
  pending ??= (async () => {
    if (typeof navigator === 'undefined' || !('gpu' in navigator)) return null;
    try {
      const gpu = await init({ powerPreference: 'high-performance' });
      void gpu.lost.then(() => document.documentElement.classList.add('gpu-lost'));
      return gpu;
    } catch {
      return null;
    }
  })();
  return pending;
}

export function reducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Calls `onChange(true)` while `el` is on screen and the page is visible, `onChange(false)` otherwise. */
export function watchVisibility(el: Element, onChange: (visible: boolean) => void, rootMargin = '120px'): () => void {
  let onScreen = false;
  let last: boolean | undefined;
  const update = () => {
    const visible = onScreen && document.visibilityState === 'visible';
    if (visible !== last) {
      last = visible;
      onChange(visible);
    }
  };
  const observer = new IntersectionObserver(
    (entries) => {
      onScreen = entries.some((e) => e.isIntersecting);
      update();
    },
    { rootMargin },
  );
  observer.observe(el);
  document.addEventListener('visibilitychange', update);
  // Decide now from layout rather than waiting for the observer's first callback.
  const r = el.getBoundingClientRect();
  onScreen = r.bottom > 0 && r.top < window.innerHeight;
  update();
  return () => {
    observer.disconnect();
    document.removeEventListener('visibilitychange', update);
  };
}

/** Drawing-buffer size for a canvas: device pixels capped by a ratio and a pixel budget. */
export function bufferSize(el: Element, maxDpr: number, maxPixels: number): [number, number] {
  const rect = el.getBoundingClientRect();
  const dpr = Math.min(maxDpr, Math.max(1, window.devicePixelRatio || 1));
  let w = Math.max(1, rect.width * dpr);
  let h = Math.max(1, rect.height * dpr);
  const scale = Math.min(1, Math.sqrt(maxPixels / (w * h)));
  w = Math.max(1, Math.round(w * scale));
  h = Math.max(1, Math.round(h * scale));
  return [w, h];
}

/** 32 digest bytes as eight little-endian words, the way the shaders read them. */
export function digestWords(bytes: Uint8Array): { a: [number, number, number, number]; b: [number, number, number, number] } {
  const w = new Uint32Array(8);
  for (let i = 0; i < 32; i++) w[i >> 2] = (w[i >> 2]! | (bytes[i]! << (8 * (i & 3)))) >>> 0;
  return { a: [w[0]!, w[1]!, w[2]!, w[3]!], b: [w[4]!, w[5]!, w[6]!, w[7]!] };
}
