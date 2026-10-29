/**
 * Living photographs: each Backdrop's photo is redrawn on a canvas by
 * living.wgsl with the motion its slot asks for (MOTIONS below), so the stills
 * read like footage. One vgpu device and one frame loop serve every canvas;
 * a canvas is set up when its section comes near, drawn only while on screen,
 * and fades in over the static <img>, which stays underneath as the fallback.
 *
 * The page talks to it through DOM events: `tb:pulse` on a section (the hero's
 * hash box sends one per keystroke) and clicks on a section, which both start
 * that photo's pulse (a wave down the fibers, a new drop, a strike...).
 */
import { effect, frameLoop, sampler, surface, texture, type Effect, type FrameLoopHandle, type Gpu, type Surface, type Texture } from 'vgpu';
import { getGpu } from './gpu';
import livingWgsl from './shaders/living.wgsl';

interface Motion {
  mode: number;
  /** A point in image uv the motion is built around. */
  anchor?: [number, number];
  /** A direction in image uv the motion flows along. */
  flow?: [number, number];
  intensity?: number;
  /** Device-pixel cap for this canvas: big soft backgrounds need fewer. */
  maxDpr?: number;
}

// Anchors were read off the photographs themselves (brightest point, horizon, whorl).
const MOTIONS: Record<string, Motion> = {
  hero: { mode: 0, anchor: [0.722, 0.498], maxDpr: 2 },
  speed: { mode: 9, flow: [0.85, 0.55] },
  'tile-model': { mode: 9, flow: [0.2, 1], maxDpr: 2 },
  versus: { mode: 1 },
  things: { mode: 2 },
  checksum: { mode: 3, anchor: [0.83, 0.42] },
  'tile-fingerprint': { mode: 4, anchor: [0.82, 0.68], maxDpr: 2 },
  why: { mode: 5 },
  'tile-fast': { mode: 6, maxDpr: 2 },
  how: { mode: 7, anchor: [0, 0.11], flow: [1, 0.31] },
  news: { mode: 8, anchor: [0.5, 0.698] },
  'tile-news': { mode: 9, flow: [1, 0.35], maxDpr: 2 },
  install: { mode: 10, anchor: [0.5, 0.515] },
};

// Pulses older than this no longer show; the shader reads `pulse` as an age in seconds.
const NO_PULSE = 99;
// HDR screens: draw into an extended float canvas and let highlights go past
// white, up to this many times SDR white. SDR screens get 1 (no change).
const HDR = typeof matchMedia === 'function' && matchMedia('(dynamic-range: high)').matches;
const HEADROOM = HDR ? 2.4 : 1;

// The motion is slow: 60 frames a second is plenty, even on 120 Hz screens.
const MIN_FRAME_MS = 1000 / 62;

interface Live {
  host: HTMLElement;
  section: HTMLElement;
  out: Surface;
  fx: Effect;
  tex: Texture;
  motion: Motion;
  image: [number, number];
  focus: [number, number];
  seed: number;
  time: number;
  pulseAt: number;
  pointer: { x: number; y: number; tx: number; ty: number };
  onScreen: boolean;
  drawn: boolean;
  greeted: boolean;
}

const lives: Live[] = [];
let loop: FrameLoopHandle | undefined;
let last = 0;

/** CSS object-position (percentages) as 0..1. */
function focusOf(img: HTMLImageElement): [number, number] {
  const [x = '50%', y = '50%'] = getComputedStyle(img).objectPosition.split(' ');
  const pct = (v: string) => (v.endsWith('%') ? parseFloat(v) / 100 : 0.5);
  return [pct(x), pct(y)];
}

async function loaded(img: HTMLImageElement): Promise<void> {
  if (!img.complete || !img.naturalWidth) {
    await new Promise<void>((resolve, reject) => {
      img.addEventListener('load', () => resolve(), { once: true });
      img.addEventListener('error', () => reject(new Error(`living: ${img.currentSrc} failed`)), { once: true });
    });
  }
  await img.decode().catch(() => undefined);
}

async function mount(gpu: Gpu, host: HTMLElement, motion: Motion): Promise<void> {
  const img = host.querySelector('img');
  const section = host.closest<HTMLElement>('section') ?? host;
  if (!img) return;
  // Mounting starts before the lazy image is requested; ask for it now.
  img.loading = 'eager';
  await loaded(img);
  // Upload only as many pixels as the canvas can show: the photo cover-cropped
  // into the box at the canvas's capped density (a 4K photo is 33 MB on the GPU).
  const box = host.getBoundingClientRect();
  const ratio = img.naturalWidth / img.naturalHeight;
  const dpr = Math.min(motion.maxDpr ?? 1.5, Math.max(1, window.devicePixelRatio || 1));
  const shown = Math.max(box.width, box.height * ratio, window.innerWidth) * dpr;
  const width = Math.min(img.naturalWidth, Math.ceil(shown));
  const bitmap = await createImageBitmap(img, { resizeWidth: width, resizeHeight: Math.round(width / ratio), resizeQuality: 'high' });
  const size: [number, number] = [bitmap.width, bitmap.height];

  const tex = texture(gpu, { kind: '2d', size, format: 'rgba8unorm', usage: ['texture_binding', 'copy_dst', 'render_attachment'], label: `living-${host.dataset.motion}` });
  gpu.gpu.queue.copyExternalImageToTexture({ source: bitmap }, { texture: tex.gpu }, size);
  bitmap.close();

  const canvas = document.createElement('canvas');
  canvas.className = 'living';
  canvas.setAttribute('aria-hidden', 'true');
  img.parentElement!.after(canvas);
  const out = surface(gpu, canvas, { dpr: [1, motion.maxDpr ?? 1.5], label: `living-${host.dataset.motion}`, ...(HDR ? { format: 'rgba16float' as const } : {}) });
  if (HDR) {
    // vgpu configures the context once; reconfigure the same format with extended
    // tone mapping, so values above 1 reach the display's headroom instead of clipping.
    try {
      // The usage vgpu itself configures: RENDER_ATTACHMENT | TEXTURE_BINDING | COPY_SRC.
      const usage = 0x10 | 0x04 | 0x01;
      const config = { device: gpu.gpu, format: out.format, alphaMode: 'premultiplied', colorSpace: 'srgb', usage, toneMapping: { mode: 'extended' } };
      out.context.configure(config as unknown as Parameters<typeof out.context.configure>[0]);
    } catch {
      // Older browsers without canvas tone mapping simply clip, as on SDR.
    }
  }
  const fx = effect(gpu, livingWgsl, {
    label: `living-${host.dataset.motion}`,
    set: {
      photo: tex,
      samp: sharedSampler(gpu),
      params: {
        canvas: [1, 1],
        image: size,
        focus: [0.5, 0.5],
        pointer: [-10, -10],
        anchor: motion.anchor ?? [0.5, 0.5],
        flow: motion.flow ?? [1, 0],
        time: 0,
        mode: motion.mode,
        headroom: HEADROOM,
        scroll: 0,
        pulse: NO_PULSE,
        intensity: motion.intensity ?? 1,
        zoom: 1.08,
        seed: 0,
      },
    },
  });
  await fx.compile({ colors: [out.format] });

  const live: Live = {
    host,
    section,
    out,
    fx,
    tex,
    motion,
    image: size,
    focus: focusOf(img),
    seed: Math.random() * 100,
    // Start somewhere along each cycle so two visits never open on the same frame.
    time: 20 + Math.random() * 60,
    pulseAt: -1e9,
    pointer: { x: -10, y: -10, tx: -10, ty: -10 },
    onScreen: false,
    drawn: false,
    greeted: false,
  };
  lives.push(live);

  // Phones swap object-position at a breakpoint; re-read it when the canvas resizes.
  out.onResize(() => {
    live.focus = focusOf(img);
  });

  new IntersectionObserver((entries) => {
    live.onScreen = entries.some((e) => e.isIntersecting);
    schedule();
  }).observe(host);
  // The first time a photo is well in view it greets you with its pulse:
  // a strike, a drop, a wave down the tree.
  const greet = new IntersectionObserver(
    (entries) => {
      if (!entries.some((e) => e.isIntersecting) || live.greeted) return;
      live.greeted = true;
      greet.disconnect();
      live.pulseAt = performance.now() + 350;
    },
    { threshold: 0.35 },
  );
  greet.observe(host);

  const pulse = () => {
    live.pulseAt = performance.now();
  };
  section.addEventListener('tb:pulse', pulse);
  section.addEventListener('pointerdown', (e) => {
    if (!(e.target as Element).closest('a, button, input, label, textarea, select, pre, code')) pulse();
  });
}

let samp: ReturnType<typeof sampler> | undefined;
function sharedSampler(gpu: Gpu) {
  samp ??= sampler(gpu, { minFilter: 'linear', magFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' });
  return samp;
}

function draw(live: Live, dt: number, now: number): void {
  live.time += dt;
  const r = live.host.getBoundingClientRect();
  const vh = window.innerHeight;
  const scroll = Math.max(-1, Math.min(1, (vh / 2 - (r.top + r.height / 2)) / (vh / 2 + r.height / 2)));
  const p = live.pointer;
  const k = Math.min(1, dt * 6);
  // Snap on entry so the lamp does not slide in from the corner.
  if (p.x < -5) {
    p.x = p.tx;
    p.y = p.ty;
  } else {
    p.x += (p.tx - p.x) * k;
    p.y += (p.ty - p.y) * k;
  }
  live.fx.set({
    params: {
      canvas: [live.out.size[0], live.out.size[1]],
      focus: live.focus,
      pointer: p.tx < -5 ? [-10, -10] : [p.x, p.y],
      time: live.time,
      scroll,
      pulse: now < live.pulseAt ? NO_PULSE : Math.min(NO_PULSE, (now - live.pulseAt) / 1000),
      seed: live.seed,
    },
  });
}

function schedule(): void {
  const any = document.visibilityState === 'visible' && lives.some((l) => l.onScreen);
  if (any && !loop) start();
  else if (!any && loop) stop();
}

let gpuRef: Gpu | undefined;
function start(): void {
  if (!gpuRef) return;
  last = performance.now();
  loop = frameLoop(gpuRef, (f) => {
    const now = performance.now();
    if (now - last < MIN_FRAME_MS) return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    for (const live of lives) {
      if (!live.onScreen) continue;
      draw(live, dt, now);
      f.pass({ target: live.out, clear: [0, 0, 0, 1] }, (pass) => pass.draw(live.fx));
      if (!live.drawn) {
        live.drawn = true;
        // Let the first frame reach the screen before the canvas covers the <img>.
        requestAnimationFrame(() => live.host.classList.add('is-live'));
      }
    }
  });
}

function stop(): void {
  loop?.stop();
  loop = undefined;
}

function onPointer(e: PointerEvent): void {
  for (const live of lives) {
    if (!live.onScreen) continue;
    const r = live.host.getBoundingClientRect();
    const x = (e.clientX - r.left) / Math.max(1, r.width);
    const y = (e.clientY - r.top) / Math.max(1, r.height);
    const inside = x >= 0 && x <= 1 && y >= 0 && y <= 1;
    live.pointer.tx = inside ? x : -10;
    live.pointer.ty = inside ? y : -10;
    if (!inside) live.pointer.x = -10;
  }
}

/** Find every backdrop with a motion and bring it to life as it comes near. */
export async function startLiving(): Promise<void> {
  const hosts = [...document.querySelectorAll<HTMLElement>('.backdrop[data-motion]')].filter((h) => MOTIONS[h.dataset.motion!]);
  if (!hosts.length) return;
  const gpu = await getGpu();
  if (!gpu) return;
  gpuRef = gpu;

  const near = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        near.unobserve(e.target);
        const host = e.target as HTMLElement;
        mount(gpu, host, MOTIONS[host.dataset.motion!]!).catch((error) => console.warn('living: keeping the still photo', error));
      }
    },
    { rootMargin: '600px 0px' },
  );
  hosts.forEach((h) => near.observe(h));

  window.addEventListener('pointermove', onPointer, { passive: true });
  document.documentElement.addEventListener('pointerleave', () => {
    for (const live of lives) live.pointer.tx = live.pointer.ty = live.pointer.x = -10;
  });
  document.addEventListener('visibilitychange', schedule);
  void gpu.lost.then(() => {
    stop();
    for (const live of lives) live.host.classList.remove('is-live');
  });
}
