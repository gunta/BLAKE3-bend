/**
 * The hero canvas: merge.wgsl into an HDR target, a two-band bloom, then
 * composite.wgsl onto the canvas. The page talks to it through the returned
 * handle: `pulse(digest)` sends a keystroke's wave down the tree and swaps the
 * beam's bits when it lands; `boost()` floors it for a moment.
 */
import { effect, frameLoop, sampler, surface, target, type Frame, type FrameLoopHandle, type Gpu, type Target } from 'vgpu';
import { bufferSize, digestWords, reducedMotion, watchVisibility } from './gpu';
import blurWgsl from './shaders/blur.wgsl';
import brightWgsl from './shaders/bright.wgsl';
import compositeWgsl from './shaders/composite.wgsl';
import mergeWgsl from './shaders/merge.wgsl';

export interface HeroHandle {
  pulse(digest: Uint8Array): void;
  boost(): void;
  dispose(): void;
}

const HDR = 'rgba16float' as const;
const CLEAR = [0, 0, 0, 1] as const;
// The scene is the expensive pass: cap its pixels and let the composite upscale.
const SCENE_MAX_DPR = 1.5;
const SCENE_MAX_PIXELS = 2_200_000;
const LENS = 0.34;
const INTRO_SECONDS = 1.7;
const WAVE_SPEED = 1.5; // tree widths per second

/**
 * Where the tree sits, in scene pixels: right of the copy when the hero is wide;
 * when it is tall, in the open space above the copy (`freeTop`/`freeBottom`,
 * the band between the header and the copy), or under the copy if that band is thin.
 */
function treeBox(w: number, h: number, freeTop: number, freeBottom: number, pixelRatio: number): [number, number, number, number] {
  if (w / h >= 1.15) {
    const x0 = -0.05 * w;
    const rootX = 0.745 * w;
    return [x0, 0.53 * h, x0 + (rootX - x0) / 0.9, 0.36 * h];
  }
  const x0 = -0.08 * w;
  const rootX = 0.8 * w;
  const x1 = x0 + (rootX - x0) / 0.9;
  const band = freeBottom - freeTop;
  if (band > 140 * pixelRatio) return [x0, (freeTop + freeBottom) / 2, x1, band * 0.4];
  return [x0, 0.79 * h, x1, 0.15 * h];
}

export async function mountHero(gpu: Gpu, canvas: HTMLCanvasElement, host: HTMLElement, initial: Uint8Array): Promise<HeroHandle> {
  const still = reducedMotion();
  const out = surface(gpu, canvas, { dpr: [1, 2], label: 'hero' });
  const linear = sampler(gpu, { minFilter: 'linear', magFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' });

  const sceneSize = () => bufferSize(canvas, SCENE_MAX_DPR, SCENE_MAX_PIXELS);
  const scaled = (s: readonly [number, number], d: number): [number, number] => [Math.max(1, Math.round(s[0] / d)), Math.max(1, Math.round(s[1] / d))];
  let size = sceneSize();
  const scene = target(gpu, { size, format: HDR, label: 'hero-scene' });
  const near: [Target, Target] = [target(gpu, { size: scaled(size, 2), format: HDR }), target(gpu, { size: scaled(size, 2), format: HDR })];
  const far: [Target, Target] = [target(gpu, { size: scaled(size, 4), format: HDR }), target(gpu, { size: scaled(size, 4), format: HDR })];

  const digest = digestWords(initial);
  const merge = effect(gpu, mergeWgsl, {
    label: 'hero-merge',
    set: {
      params: {
        resolution: [1, 1],
        pointer: [-1e5, -1e5],
        tree: [0, 0, 1, 1],
        time: 0,
        intro: still ? 1 : 0,
        kick: 0,
        speed: 1,
        lens: 0,
        lensRadius: 150,
        pixelRatio: 1,
        wave: 9,
        digestA: digest.a,
        digestB: digest.b,
      },
    },
  });
  const bright = effect(gpu, brightWgsl, { label: 'hero-bright', set: { samp: linear, bright: { threshold: 0.12, knee: 0.4 } } });
  const blurs = [
    { src: near[0], dir: [1, 0], radius: 1.3 },
    { src: near[1], dir: [0, 1], radius: 1.3 },
    { src: near[0], dir: [1, 0], radius: 2.4 },
    { src: far[0], dir: [0, 1], radius: 2.4 },
  ].map((b, i) => effect(gpu, blurWgsl, { label: `hero-blur-${i}`, set: { samp: linear, blur: { texelSize: [1, 1], direction: b.dir, radius: b.radius } } }));
  const blurSources = [near[0], near[1], near[0], far[0]];
  const composite = effect(gpu, compositeWgsl, {
    label: 'hero-composite',
    set: {
      samp: linear,
      params: { exposure: 1.05, bloomNear: 0.9, bloomFar: 0.75, aberration: 0.012, grain: 0.022, time: 0, fade: 0.16, pad: 0 },
    },
  });

  const bind = () => {
    const [w, h] = scene.size;
    const rect = canvas.getBoundingClientRect();
    const pixelRatio = w / Math.max(1, rect.width);
    // The open band above the copy, below the fixed header, in scene pixels.
    const copy = host.querySelector('.content')?.getBoundingClientRect();
    const freeTop = 72 * pixelRatio;
    const freeBottom = copy ? (copy.top - rect.top - 16) * pixelRatio : 0;
    merge.set({ params: { resolution: [w, h], tree: treeBox(w, h, freeTop, freeBottom, pixelRatio), pixelRatio, lensRadius: 150 } });
    bright.set({ src: scene });
    blurs.forEach((b, i) => b.set({ src: blurSources[i]!, blur: { texelSize: blurSources[i]!.texelSize } }));
    composite.set({ scene, near: near[0], far: far[1] });
  };
  bind();
  // Web fonts can move the copy after first layout; re-fit the tree once they are in.
  void document.fonts?.ready.then(() => {
    if (!gpu.disposed) bind();
  });

  await Promise.all([
    merge.compile(scene),
    bright.compile(near[0]),
    ...blurs.map((b, i) => b.compile([near[1], near[0], far[0], far[1]][i]!)),
    composite.compile({ colors: [out.format] }),
  ]);

  // Animation state, advanced by our own clock so pausing off screen does not jump.
  let time = 0;
  let intro = still ? 1 : 0;
  // The intro runs on the wall clock from the first drawn frame, so a throttled tab cannot stall it.
  let introStart = 0;
  let kick = 0;
  let wave = 9;
  let speed = 1;
  let speedTarget = 1;
  let boostUntil = 0;
  let lens = 0;
  let lensTarget = 0;
  let pending: Uint8Array | undefined;
  const pointer = { x: -1e5, y: -1e5, tx: -1e5, ty: -1e5 };

  const setDigest = (bytes: Uint8Array) => {
    const d = digestWords(bytes);
    merge.set({ params: { digestA: d.a, digestB: d.b } });
  };

  const draw = (dt: number) => {
    time += dt;
    if (!still) {
      introStart ||= performance.now();
      intro = Math.min(1, (performance.now() - introStart) / 1000 / INTRO_SECONDS);
    }
    if (wave < 2) {
      const before = wave;
      wave += dt * WAVE_SPEED;
      // The wave lands on the root: the beam takes the new digest and the root kicks.
      if (before < 0.9 && wave >= 0.9) {
        kick = 1;
        if (pending) setDigest(pending);
        pending = undefined;
      }
    }
    kick *= Math.exp(-dt * 3.2);
    if (performance.now() > boostUntil) speedTarget = 1;
    const scroll = Math.min(1, Math.max(0, -host.getBoundingClientRect().top / Math.max(1, host.offsetHeight)));
    speed += (speedTarget + scroll * 2.2 - speed) * Math.min(1, dt * 4);
    lens += (lensTarget - lens) * Math.min(1, dt * 5);
    pointer.x += (pointer.tx - pointer.x) * Math.min(1, dt * 9);
    pointer.y += (pointer.ty - pointer.y) * Math.min(1, dt * 9);

    merge.set({ params: { time, intro, kick, wave, speed, lens, pointer: [pointer.x, pointer.y] } });
    composite.set({ params: { time } });
    frameOnce();
  };

  // One frame of the chain. Inside a frameLoop tick it encodes into that frame.
  let current: Frame | undefined;
  const frameOnce = () => {
    const f = current;
    if (!f) return;
    f.pass({ target: scene, clear: CLEAR }, (p) => p.draw(merge));
    f.pass({ target: near[0], clear: CLEAR }, (p) => p.draw(bright));
    f.pass({ target: near[1], clear: CLEAR }, (p) => p.draw(blurs[0]!));
    f.pass({ target: near[0], clear: CLEAR }, (p) => p.draw(blurs[1]!));
    f.pass({ target: far[0], clear: CLEAR }, (p) => p.draw(blurs[2]!));
    f.pass({ target: far[1], clear: CLEAR }, (p) => p.draw(blurs[3]!));
    f.pass({ target: out, clear: CLEAR }, (p) => p.draw(composite));
  };

  let loop: FrameLoopHandle | undefined;
  let last = 0;
  const start = () => {
    if (loop) return;
    last = performance.now();
    loop = frameLoop(gpu, (f) => {
      const now = performance.now();
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      current = f;
      draw(still ? 0 : dt);
      current = undefined;
    });
  };
  const stop = () => {
    loop?.stop();
    loop = undefined;
  };

  // Reduced motion: no loop; draw a frame when something changes.
  const nudge = () => {
    if (!still || loop) return;
    start();
    requestAnimationFrame(() => requestAnimationFrame(stop));
  };

  // Re-fit the offscreen chain whenever the canvas changes size (onResize also fires once right away).
  const stopResize = out.onResize(() => {
    const next = sceneSize();
    if (next[0] === size[0] && next[1] === size[1]) return;
    size = next;
    scene.resize(size);
    near.forEach((t) => t.resize(scaled(size, 2)));
    far.forEach((t) => t.resize(scaled(size, 4)));
    bind();
    nudge();
  });

  const stopVisibility = watchVisibility(host, (visible) => {
    if (still) {
      if (visible) nudge();
      return;
    }
    if (visible) start();
    else stop();
  });

  // The pointer bends the field while it is over the hero.
  const toCanvas = (e: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    const sx = scene.size[0] / Math.max(1, rect.width);
    const sy = scene.size[1] / Math.max(1, rect.height);
    return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy, inside: e.clientY >= rect.top && e.clientY <= rect.bottom };
  };
  const onMove = (e: PointerEvent) => {
    const p = toCanvas(e);
    if (pointer.tx < -1e4) {
      pointer.x = p.x;
      pointer.y = p.y;
    }
    pointer.tx = p.x;
    pointer.ty = p.y;
    lensTarget = p.inside && !still ? LENS : 0;
  };
  const onLeave = () => {
    lensTarget = 0;
  };
  window.addEventListener('pointermove', onMove, { passive: true });
  document.documentElement.addEventListener('pointerleave', onLeave);

  return {
    pulse(bytes: Uint8Array) {
      if (still) {
        setDigest(bytes);
        nudge();
        return;
      }
      pending = bytes;
      wave = -0.08;
    },
    boost() {
      if (still) return;
      speedTarget = 4.5;
      boostUntil = performance.now() + 900;
      kick = Math.max(kick, 0.6);
    },
    dispose() {
      stop();
      stopVisibility();
      stopResize();
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
      for (const e of [merge, bright, ...blurs, composite]) e.dispose();
      for (const t of [scene, ...near, ...far]) (t as { destroy?: () => void }).destroy?.();
      out.dispose();
    },
  };
}
