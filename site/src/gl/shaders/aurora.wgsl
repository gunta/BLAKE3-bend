// The install section's backdrop: three curtains of light in the brand's two
// colors, drifting slowly over the page background. Each curtain is a wavy
// bright edge with soft rays rising from it; the pointer warms the light near
// it. Written straight to the canvas in display (sRGB) values, no bloom chain,
// so it stays cheap enough to run behind text. Top and bottom fade into the
// page so the section has no seams.

import { hash2 } from "@vgpu/wgsl-std/hash";
import { simplex3d } from "@vgpu/wgsl-std/noise/simplex";

struct Params {
  resolution: vec2f,
  // pointer in uv, or far away when it is not over the section
  pointer: vec2f,
  time: f32,
  // 0 to 1: fades the light in the first time the section is drawn
  intro: f32,
  pad0: f32,
  pad1: f32,
}

@group(0) @binding(0) var<uniform> params: Params;

// #060608, #d4ff3a, #46e3ff
const VOID = vec3f(0.0235, 0.0235, 0.0314);
const VOLT = vec3f(0.831, 1.0, 0.227);
const ION = vec3f(0.275, 0.890, 1.0);

// One curtain: brightness at `p` (y up), with its edge near `base`.
fn curtain(p: vec2f, t: f32, base: f32, seed: f32) -> f32 {
  let edge = base
    + 0.16 * simplex3d(vec3f(p.x * 0.7 + seed * 5.0, t * 0.05, seed))
    + 0.05 * simplex3d(vec3f(p.x * 2.3 - seed * 3.0, t * 0.09, seed + 7.0));
  let dy = p.y - edge;
  // A sharp lower edge, a long soft fall-off upward.
  let lower = smoothstep(-0.035, 0.0, dy);
  let upper = exp(-max(dy, 0.0) * 4.2);
  // Rays: noise stretched along y, sliding sideways.
  let rays = 0.55 + 0.45 * simplex3d(vec3f(p.x * 11.0 + t * 0.06, p.y * 0.6, seed * 3.0 + t * 0.04));
  return lower * upper * rays;
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let aspect = params.resolution.x / max(1.0, params.resolution.y);
  let p = vec2f((uv.x - 0.5) * aspect, 0.5 - uv.y);
  // Keep time small: simplex wants bounded input.
  let t = params.time % 2000.0;

  var light = vec3f(0.0);
  let a = curtain(p, t, -0.2, 0.0);
  let b = curtain(p, t, -0.02, 1.0);
  let c = curtain(p, t, 0.16, 2.0);
  // Each curtain blends ion to volt along its length, offset from the others.
  let hue = smoothstep(-0.8, 0.8, p.x + 0.25 * sin(t * 0.07));
  light += a * mix(ION, VOLT, hue) * 0.55;
  light += b * mix(VOLT, ION, hue) * 0.4;
  light += c * ION * 0.22;

  // The pointer warms the curtains near it.
  let d = distance(uv * vec2f(aspect, 1.0), params.pointer * vec2f(aspect, 1.0));
  light *= 1.0 + 0.9 * exp(-d * d * 18.0);

  // Fade into the page at the top and bottom, and toward the sides.
  let fade = smoothstep(0.0, 0.22, uv.y) * smoothstep(1.0, 0.7, uv.y);
  let side = smoothstep(1.25, 0.25, abs(uv.x - 0.5) * 2.0);
  light *= fade * mix(0.55, 1.0, side) * params.intro;

  var color = VOID + light * (1.0 - 0.35 * light);
  let noise = hash2(floor(uv * params.resolution) + fract(t * 7.0) * 97.0).x - 0.5;
  color += noise * 0.012;
  return vec4f(color, 1.0);
}
