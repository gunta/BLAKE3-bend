/** The footer's checkered flag: one effect, straight onto its canvas, only while on screen. */
import { effect, frameLoop, surface, type FrameLoopHandle, type Gpu } from 'vgpu';
import { reducedMotion, watchVisibility } from './gpu';
import flagWgsl from './shaders/flag.wgsl';

export async function mountFlag(gpu: Gpu, canvas: HTMLCanvasElement, host: HTMLElement): Promise<() => void> {
  const still = reducedMotion();
  const out = surface(gpu, canvas, { dpr: [1, 1.5], label: 'flag' });
  const flag = effect(gpu, flagWgsl, {
    label: 'flag',
    set: { params: { resolution: [1, 1], pointer: [-1e4, -1e4], time: 0, pixelRatio: 1, push: 0, pad: 0 } },
  });
  await flag.compile({ colors: [out.format] });

  let time = 4;
  let push = 0;
  let last = 0;
  let px = -1e4;
  let py = -1e4;
  let loop: FrameLoopHandle | undefined;

  const stopResize = out.onResize(({ width, height }) => {
    flag.set({ params: { resolution: [width, height], pixelRatio: width / Math.max(1, canvas.getBoundingClientRect().width) } });
  });

  const start = () => {
    if (loop) return;
    last = performance.now();
    loop = frameLoop(gpu, (f) => {
      const now = performance.now();
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!still) time += dt;
      push *= Math.exp(-dt * 1.6);
      flag.set({ params: { time, push, pointer: [px, py] } });
      f.pass({ target: out, clear: [0, 0, 0, 1] }, (p) => p.draw(flag));
      if (still) stop();
    });
  };
  const stop = () => {
    loop?.stop();
    loop = undefined;
  };

  const onMove = (e: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    const s = out.size[0] / Math.max(1, rect.width);
    const nx = (e.clientX - rect.left) * s;
    const ny = (e.clientY - rect.top) * s;
    const moved = px < -1e3 ? 0 : Math.hypot(nx - px, ny - py) / s;
    px = nx;
    py = ny;
    push = Math.min(1, push + moved * 0.004);
  };
  host.addEventListener('pointermove', onMove, { passive: true });
  const stopVisibility = watchVisibility(host, (visible) => (visible ? start() : stop()));

  return () => {
    stop();
    stopVisibility();
    stopResize();
    host.removeEventListener('pointermove', onMove);
    flag.dispose();
    out.dispose();
  };
}
