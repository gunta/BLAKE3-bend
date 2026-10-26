/**
 * The install section's canvas: aurora.wgsl straight onto the canvas, one pass.
 * Runs only while the section is on screen; with reduced motion it draws one
 * still frame. Returns a dispose function.
 */
import { effect, frameLoop, surface, type FrameLoopHandle, type Gpu } from 'vgpu';
import { reducedMotion, watchVisibility } from './gpu';
import auroraWgsl from './shaders/aurora.wgsl';

const INTRO_SECONDS = 1.6;

export async function mountAurora(gpu: Gpu, canvas: HTMLCanvasElement, host: HTMLElement): Promise<() => void> {
  const still = reducedMotion();
  // A soft field: no need for full device pixels.
  const out = surface(gpu, canvas, { dpr: [1, 1.25], label: 'aurora' });
  const fx = effect(gpu, auroraWgsl, {
    label: 'aurora',
    set: { params: { resolution: [1, 1], pointer: [-10, -10], time: 0, intro: still ? 1 : 0, pad0: 0, pad1: 0 } },
  });
  await fx.compile({ colors: [out.format] });

  // Start somewhere along the drift so the first frame is not the same every visit.
  let time = Math.random() * 400;
  let introStart = 0;
  const pointer = { x: -10, y: -10, tx: -10, ty: -10 };

  let loop: FrameLoopHandle | undefined;
  let last = 0;
  const start = () => {
    if (loop) return;
    last = performance.now();
    loop = frameLoop(gpu, (f) => {
      const now = performance.now();
      const dt = still ? 0 : Math.min(0.05, (now - last) / 1000);
      last = now;
      time += dt;
      introStart ||= now;
      const intro = still ? 1 : Math.min(1, (now - introStart) / 1000 / INTRO_SECONDS);
      pointer.x += (pointer.tx - pointer.x) * Math.min(1, dt * 4);
      pointer.y += (pointer.ty - pointer.y) * Math.min(1, dt * 4);
      fx.set({ params: { resolution: [out.size[0], out.size[1]], pointer: [pointer.x, pointer.y], time, intro } });
      f.pass({ target: out, clear: [0, 0, 0, 1] }, (p) => p.draw(fx));
    });
  };
  const stop = () => {
    loop?.stop();
    loop = undefined;
  };

  // Reduced motion: one frame whenever it comes on screen or changes size.
  const nudge = () => {
    if (!still) return;
    start();
    requestAnimationFrame(() => requestAnimationFrame(stop));
  };
  const stopResize = out.onResize(nudge);

  const stopVisibility = watchVisibility(host, (visible) => {
    if (still) {
      if (visible) nudge();
    } else if (visible) start();
    else stop();
  });

  const onMove = (e: PointerEvent) => {
    const r = canvas.getBoundingClientRect();
    const x = (e.clientX - r.left) / Math.max(1, r.width);
    const y = (e.clientY - r.top) / Math.max(1, r.height);
    const inside = x >= 0 && x <= 1 && y >= 0 && y <= 1;
    if (inside && pointer.tx < -5) {
      pointer.x = x;
      pointer.y = y;
    }
    pointer.tx = inside ? x : -10;
    pointer.ty = inside ? y : -10;
  };
  host.addEventListener('pointermove', onMove, { passive: true });
  host.addEventListener('pointerleave', () => {
    pointer.tx = -10;
    pointer.ty = -10;
  });

  return () => {
    stop();
    stopResize();
    stopVisibility();
    host.removeEventListener('pointermove', onMove);
    out.dispose();
  };
}
