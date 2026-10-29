/**
 * One vgpu context for every canvas on the page; null where WebGPU is missing,
 * so the page keeps its still photographs.
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
