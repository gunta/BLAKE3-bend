// Living photographs: every backdrop photo, redrawn on the GPU with its own
// motion, so the still reads like footage. One shader, one `mode` per photo:
//
//   0 fibers    light packets run down the fiber tree into the root; the
//               root breathes, the beam carries them on; a keystroke sends a
//               bright wave (BLAKE3's tree, merging toward one digest)
//   1 river     a sheen drifts down the channels toward the main river
//   2 leds      drive-bay LEDs blink, a read sweeps along the rows
//   3 scan      rings of light sweep out from the fingerprint's whorl
//   4 ripple    the water keeps rippling; a new drop lands every few seconds
//   5 crystal   glints catch on the facets, a slow light sweeps across
//   6 lightning the bolt flickers and strikes again
//   7 veins     light flows out of the midrib, along the veins
//   8 horizon   the line of first light shimmers; the ground reflects it
//   9 chip      a scan beam crosses the silicon, packets flash on the traces
//  10 aurora    the curtains sway, rays flicker, the lake ripples
//
// Shared by all: cover-cropping like CSS object-fit (with the same focus), a
// slow drift, scroll parallax, a pointer light that only lifts what is
// already lit, a vivid grade and film grain. Output is display (sRGB-encoded)
// values. On an SDR canvas the light is screened onto the photo, so highlights
// roll off instead of clipping; on an HDR canvas (`headroom` > 1, an extended
// float canvas) the light is added on top and the photo's own highlights are
// lifted past white, so the root, the packets and the strikes truly glow.

import { hash2 } from "@vgpu/wgsl-std/hash";
import { simplex3d } from "@vgpu/wgsl-std/noise/simplex";

struct Params {
  canvas: vec2f,
  image: vec2f,
  // CSS object-position as 0..1
  focus: vec2f,
  // pointer in canvas uv; far away when not over the section
  pointer: vec2f,
  // a point in image uv the motion is built around (root, drop, whorl...)
  anchor: vec2f,
  // a direction in image uv the motion flows along
  flow: vec2f,
  time: f32,
  mode: f32,
  // how far past SDR white the display can go (1 on SDR screens)
  headroom: f32,
  // -1 entering from below, 0 centered in the viewport, 1 leaving at the top
  scroll: f32,
  // seconds since the last pulse (a keystroke or a click); large when none
  pulse: f32,
  intensity: f32,
  zoom: f32,
  seed: f32,
}

@group(0) @binding(0) var photo: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> params: Params;

const VOLT = vec3f(0.831, 1.0, 0.227);
const ION = vec3f(0.275, 0.890, 1.0);
const LUMA = vec3f(0.2126, 0.7152, 0.0722);

fn photoAt(p: vec2f) -> vec3f {
  return textureSampleLevel(photo, samp, clamp(p, vec2f(0.0005), vec2f(0.9995)), 0.0).rgb;
}

// Highlight roll-off: linear up to `knee`, then easing smoothly into `peak` and
// never past it, so stacked light glows instead of clipping into a flat blob.
// Applied to the brightest channel and scaled back, so hue survives.
fn rolloff(c: vec3f, knee: f32, peak: f32) -> vec3f {
  let m = max(max(c.r, c.g), c.b);
  if (m <= knee) {
    return c;
  }
  let span = peak - knee;
  let rolled = knee + span * (1.0 - exp(-(m - knee) / span));
  // Past the knee the color also drifts toward white a little, like film.
  let scaled = c * (rolled / m);
  return mix(scaled, vec3f(rolled), smoothstep(knee, peak, m) * 0.35);
}

fn screen(base: vec3f, light: vec3f) -> vec3f {
  return 1.0 - (1.0 - base) * (1.0 - clamp(light, vec3f(0.0), vec3f(1.0)));
}

fn n3(p: vec3f) -> f32 {
  return simplex3d(p) * 0.5 + 0.5;
}

// How yellow-green (volt) rather than cyan (ion) a lit pixel is, 0..1.
fn voltness(c: vec3f) -> f32 {
  return smoothstep(-0.15, 0.25, c.r - c.b);
}

// A round point of light at a jittered spot in its grid cell (`q` in cell units).
fn spark(q: vec2f, h: vec2f, size: f32) -> f32 {
  let c = fract(q) - (0.25 + 0.5 * h);
  return exp(-dot(c, c) / (size * size));
}

// A traveling packet: bright leading edge, a short tail. `phase` grows along the flow.
fn packet(phase: f32, sharp: f32) -> f32 {
  let f = fract(phase);
  return exp(-f * sharp) * smoothstep(0.0, 0.02, f);
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let t = params.time % 3000.0;
  let ca = params.canvas.x / max(1.0, params.canvas.y);
  let ia = params.image.x / max(1.0, params.image.y);

  // object-fit: cover, object-position: focus.
  var span = vec2f(1.0);
  if (ca > ia) {
    span.y = ia / ca;
  } else {
    span.x = ca / ia;
  }
  let origin = (1.0 - span) * params.focus;
  var p = origin + uv * span;

  // Drift, parallax and pointer lean, inside the slack a slight zoom leaves.
  let center = origin + 0.5 * span;
  let away = params.pointer.x < -1.0;
  let lean = select((params.pointer - 0.5) * 0.012, vec2f(0.0), away);
  let drift = vec2f(sin(t * 0.05 + params.seed), cos(t * 0.041 + params.seed * 1.7)) * 0.008;
  let parallax = vec2f(0.0, params.scroll * 0.03) * span.y;
  p = center + (p - center) / params.zoom + (drift + parallax + lean) * span;

  let mode = u32(params.mode + 0.5);
  let a = params.anchor;
  let aspect = vec2f(ia, 1.0);
  var light = vec3f(0.0);
  var gain = 1.0;

  // Modes that move the pixels themselves first, then sample.
  if (mode == 4u) {
    // Ripple: rings in perspective (squashed in y), traveling outward.
    let d = (p - a) * vec2f(ia, ia * 3.4);
    let r = length(d);
    let swell = sin(r * 70.0 - t * 3.2) * exp(-r * 1.6) * 0.0016;
    let drop = params.pulse;
    let ringR = (t % 5.0) * 0.32;
    let fresh = sin((r - ringR) * 90.0) * exp(-abs(r - ringR) * 14.0) * exp(-(t % 5.0) * 0.5) * 0.004;
    let clicked = sin((r - drop * 0.4) * 90.0) * exp(-abs(r - drop * 0.4) * 14.0) * exp(-drop * 0.7) * 0.005;
    p += normalize(d + vec2f(1e-5)) * (swell + fresh + clicked) * vec2f(1.0, 0.3);
  } else if (mode == 10u) {
    // Aurora: the sky's curtains sway; below the waterline the reflection follows and ripples.
    let hy = a.y;
    let below = p.y > hy;
    let sy = select(p.y, 2.0 * hy - p.y, below);
    let sway = (n3(vec3f(p.x * 1.6, sy * 0.8, t * 0.1)) - 0.5) * 0.04;
    let curl = sin(sy * 22.0 + t * 0.5 + p.x * 3.0) * 0.0025;
    p.x += curl;
    if (below) {
      let depth = smoothstep(hy, hy + 0.04, p.y);
      // Water: ripples smeared sideways, irregular, a little stronger toward the viewer.
      let ripple = (n3(vec3f(p.x * 5.0, p.y * 150.0 - t * 0.9, t * 0.3)) - 0.5) * 0.012
        + (n3(vec3f(p.x * 14.0, p.y * 320.0 - t * 1.6, 9.0)) - 0.5) * 0.004;
      p.x += ripple * depth * (0.6 + (p.y - hy) * 2.0);
      p.y -= sway * depth;
    } else {
      p.y += sway * smoothstep(hy, hy - 0.08, p.y);
    }
  } else if (mode == 1u) {
    // River: the water itself shimmers a little.
    let base = photoAt(p);
    let wet = smoothstep(0.06, 0.3, dot(base, LUMA));
    p += (vec2f(n3(vec3f(p * 40.0, t * 0.3)), n3(vec3f(p * 40.0 + 7.0, t * 0.3))) - 0.5) * 0.0018 * wet;
  }

  var color = photoAt(p);
  let l = dot(color, LUMA);
  let lit = smoothstep(0.07, 0.45, l);

  if (mode == 0u) {
    // Fibers: packets run left to right down every fiber, merging toward the root.
    let toRoot = a.x - p.x;
    let wobble = n3(vec3f(p * vec2f(3.0, 14.0), params.seed)) * 0.25;
    let packets = packet((p.x - a.x) * 5.0 - t * 0.6 + wobble, 9.0) * 1.0
      + packet((p.x - a.x) * 11.0 - t * 1.25 + wobble * 2.0, 16.0) * 0.6;
    let hue = mix(ION, VOLT, smoothstep(0.25, 0.75, p.x / max(0.01, a.x)));
    let nearRoot = smoothstep(0.02, 0.12, toRoot);
    light += hue * packets * lit * step(0.0, toRoot) * mix(0.35, 1.0, nearRoot);
    // A keystroke: one bright front sweeps the whole tree in under a second.
    let front = params.pulse * 0.95 * a.x;
    light += mix(ION, VOLT, 0.5) * exp(-abs(p.x - front) * 45.0) * lit * step(0.0, toRoot) * exp(-params.pulse * 1.2) * 1.3;
    // The root breathes, flares as packets and pulses arrive.
    let r = length((p - a) * aspect);
    let arrive = exp(-max(params.pulse - 0.95, 0.0) * 4.0) * step(0.9, params.pulse);
    let breathe = 0.6 + 0.4 * sin(t * 1.6) + arrive * 0.7;
    light += VOLT * exp(-r * r * 3200.0) * breathe * 0.6 + VOLT * exp(-r * 45.0) * 0.06 * breathe;
    // The beam beyond the root carries the packets on.
    let beamY = exp(-abs(p.y - a.y) * 1400.0);
    light += VOLT * beamY * step(a.x, p.x) * (0.25 + packet((p.x - a.x) * 9.0 - t * 1.4, 7.0) * 0.9);
  } else if (mode == 1u) {
    // River: a slow sheen drifts downstream (toward -x) along every lit channel.
    let sheen = pow(n3(vec3f(p.x * 14.0 + t * 0.18, p.y * 20.0, t * 0.08)), 5.0);
    let surge = packet(-p.x * 1.6 - t * 0.14 + n3(vec3f(p * 3.0, 1.0)) * 0.3, 6.0);
    light += mix(ION, VOLT, voltness(color)) * (sheen * 2.2 + surge * 0.9) * lit;
  } else if (mode == 2u) {
    // LEDs: each one blinks on its own clock; a read sweeps along the rows.
    let cell = floor(p * vec2f(90.0, 34.0));
    let h = hash2(cell + params.seed);
    let blink = select(0.15 + 0.85 * step(0.45, fract(t * (0.5 + h.y * 2.5) + h.x)), 1.0, h.x < 0.25);
    let spot = smoothstep(0.12, 0.42, l);
    gain = mix(1.0, blink * 1.9, spot);
    // A soft halo around every lit LED, so the blinking reads at a glance.
    let o = vec2f(0.004, 0.009);
    let around = photoAt(p + o) + photoAt(p - o) + photoAt(p + vec2f(o.x, -o.y)) + photoAt(p + vec2f(-o.x, o.y));
    let halo = smoothstep(0.04, 0.2, dot(around * 0.25, LUMA));
    let sweep = packet(p.x * 1.4 - t * 0.35 + floor(p.y * 3.0) * 0.37, 10.0);
    light += mix(ION, VOLT, h.y) * (sweep * (spot + halo * 0.3) * 1.1 + halo * blink * 0.12);
  } else if (mode == 3u) {
    // Scan: rings sweep out from the whorl, lighting the ridges they cross.
    let r = length((p - a) * aspect);
    let ring = packet(r * 2.6 - t * 0.22, 12.0);
    let click = exp(-abs(r - params.pulse * 0.5) * 30.0) * exp(-params.pulse * 1.4);
    light += mix(VOLT, ION, smoothstep(0.05, 0.45, r)) * (ring * 1.2 + click * 2.0) * lit;
  } else if (mode == 4u) {
    // Ripple: crests catch a little more light as they pass.
    let r = length((p - a) * vec2f(ia, ia * 3.4));
    let crest = pow(max(0.0, sin(r * 70.0 - t * 3.2)), 6.0) * exp(-r * 1.4);
    light += ION * crest * lit * 0.45;
    let drop = exp(-length((p - a) * aspect) * 60.0) * (0.5 + 0.5 * sin(t * 2.0));
    light += VOLT * drop * 0.35;
  } else if (mode == 5u) {
    // Crystal: glints on the facets, and a slow sweep of light across them.
    let q = p * vec2f(ia, 1.0) * 70.0;
    let h = hash2(floor(q) + params.seed);
    let tw = pow(max(0.0, sin(t * (1.0 + h.x * 2.0) + h.y * 40.0)), 30.0);
    let c = fract(q) - (0.25 + 0.5 * h);
    // A four-point star: a round core and two thin cross arms.
    let star = exp(-dot(c, c) * 300.0) + exp(-abs(c.x) * 60.0 - abs(c.y) * 9.0) * 0.5 + exp(-abs(c.y) * 60.0 - abs(c.x) * 9.0) * 0.5;
    let glint = tw * step(0.8, h.x) * smoothstep(0.25, 0.6, l) * star;
    light += mix(ION, vec3f(1.0), 0.5) * glint * 1.8;
    let sweep = exp(-pow((p.x + p.y * 0.5 - (fract(t * 0.045) * 2.4 - 0.4)) * 7.0, 2.0));
    light += mix(ION, VOLT, voltness(color)) * sweep * lit * 0.55;
  } else if (mode == 6u) {
    // Lightning: a strike every few seconds (or on click), flickering, then an afterglow.
    let cycle = 4.5;
    let since = min(t % cycle, params.pulse);
    let flicker = step(0.35, n3(vec3f(t * 22.0, 0.0, params.seed))) * exp(-since * 3.0)
      + exp(-since * 9.0);
    let bolt = smoothstep(0.2, 0.55, l);
    gain = mix(0.72, 1.0, 1.0 - bolt) + bolt * (0.15 + flicker * 1.4);
    light += mix(ION, VOLT, voltness(color)) * bolt * flicker * 0.5 + ION * flicker * 0.05;
    // A crawl of charge down the bolt between strikes.
    light += VOLT * packet(p.y * 3.0 - t * 1.1, 14.0) * bolt * 0.25;
  } else if (mode == 7u) {
    // Veins: light leaves the midrib and runs out along the veins.
    let dir = normalize(params.flow);
    let rel = p - a;
    let along = dot(rel * aspect, dir);
    let side = abs(rel.x * aspect.x * dir.y - rel.y * dir.x);
    let flowPhase = along * 2.2 + side * 6.0 - t * 0.45;
    let veins = smoothstep(0.1, 0.5, l);
    light += mix(ION, VOLT, voltness(color)) * packet(flowPhase, 7.0) * veins * 1.1;
    let click = exp(-abs(side - params.pulse * 0.35) * 25.0) * exp(-params.pulse * 1.2);
    light += VOLT * click * veins * 1.5;
  } else if (mode == 8u) {
    // Horizon: the line of first light shimmers and glints travel along it.
    let hy = a.y;
    let line = exp(-abs(p.y - hy) * 520.0);
    let glints = pow(n3(vec3f(p.x * 9.0 - t * 0.25, 0.0, params.seed)), 6.0);
    light += VOLT * line * (0.35 + glints * 1.8 + 0.25 * sin(t * 1.3));
    let sky = smoothstep(hy, hy - 0.25, p.y) * exp(-abs(p.y - hy) * 6.0);
    light += ION * sky * (0.05 + 0.04 * sin(t * 0.4));
    let reflect = smoothstep(hy, hy + 0.12, p.y) * exp(-abs(p.y - hy) * 9.0);
    light += VOLT * reflect * pow(n3(vec3f(p.x * 20.0, p.y * 120.0 - t * 0.6, 3.0)), 4.0) * 0.3;
  } else if (mode == 9u) {
    // Chip: a scan beam crosses the silicon, packets flash along the traces.
    let dir = normalize(params.flow);
    let s = dot(p * aspect, dir) / (abs(dir.x) * ia + abs(dir.y)) - (fract(t * 0.1 + params.seed) * 1.6 - 0.3);
    let beam = exp(-s * s * 260.0);
    light += ION * beam * lit * 1.6 + ION * beam * 0.06;
    let q = p * vec2f(ia, 1.0) * 46.0;
    let h = hash2(floor(q) + params.seed);
    let flash = pow(max(0.0, sin(t * (0.7 + h.x * 1.6) + h.y * 30.0)), 24.0) * step(0.84, h.y);
    light += VOLT * flash * spark(q, h, 0.08) * smoothstep(0.15, 0.5, l) * 1.8;
    let click = exp(-abs(s + 0.2 - params.pulse * 0.9) * 18.0) * exp(-params.pulse * 1.5);
    light += VOLT * click * lit;
  } else if (mode == 10u) {
    // Aurora: rays flicker in the curtain, and its edge brightens in slow waves.
    let rays = n3(vec3f(p.x * 70.0, 0.0, t * 0.35)) * 0.6 + n3(vec3f(p.x * 18.0, 3.0, t * 0.2)) * 0.4;
    gain = 1.0 + (rays - 0.45) * 0.55 * lit;
    light += mix(ION, VOLT, voltness(color)) * packet(p.x * 1.2 - t * 0.09, 4.0) * lit * 0.55;
    let flare = exp(-params.pulse * 1.1);
    light += mix(ION, VOLT, voltness(color)) * lit * flare * 0.6;
  }

  color = color * gain;

  // A vivid grade: richer color in the mid-tones, deeper blacks. It maps white to
  // white, so the bright fibers keep their detail instead of clipping flat.
  let gray = dot(color, LUMA);
  let mids = 1.0 - smoothstep(0.55, 0.95, gray);
  color = clamp(mix(vec3f(gray), color, 1.0 + 0.25 * mids), vec3f(0.0), vec3f(1.0));
  color = mix(color, color * color * (3.0 - 2.0 * color), 0.4);

  // The pointer lifts what is lit near it, like moving a lamp over a print.
  if (!away) {
    let d = length((uv - params.pointer) * vec2f(ca, 1.0));
    let lamp = exp(-d * d * 9.0);
    light += color * lamp * 0.3 + mix(ION, VOLT, voltness(color)) * lamp * lit * 0.15;
  }

  if (params.headroom > 1.01) {
    // HDR: only the brightest specks of the photo go past white, the light is
    // added on top, and the roll-off eases everything into the display's peak.
    let hl = smoothstep(0.8, 1.0, dot(color, LUMA));
    let lifted = color * (1.0 + hl * (params.headroom - 1.0) * 0.3) + light * params.intensity * 1.4;
    color = rolloff(lifted, 1.0, params.headroom);
  } else {
    color = rolloff(screen(color, light * params.intensity), 0.86, 1.0);
  }

  // Fine grain, so the frame reads as footage rather than a flat still.
  let grain = hash2(floor(uv * params.canvas) + fract(t * 23.0) * 97.0).x - 0.5;
  color += grain * 0.022;

  return vec4f(color, 1.0);
}
