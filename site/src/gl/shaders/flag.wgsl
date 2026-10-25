// The finish line: a charcoal checkered flag rippling in the wind, lit from
// the upper right, with a volt light sweeping across it now and then. Moving
// the pointer over it pushes a ripple through the cloth. The top fades into
// the page so the footer has no edge.

import { linearToSrgb3, tonemapAces } from "@vgpu/wgsl-std/color";
import { simplex3d } from "@vgpu/wgsl-std/noise/simplex";

struct Params {
  resolution: vec2f,
  pointer: vec2f,
  time: f32,
  pixelRatio: f32,
  push: f32,
  pad: f32,
}

@group(0) @binding(0) var<uniform> params: Params;

const VOLT = vec3f(0.66, 1.0, 0.04);
const WHITE = vec3f(1.0, 1.0, 0.95);
const VOID = vec3f(0.0018, 0.0018, 0.0025);
const CELL = 64.0; // checker size in CSS pixels

// Cloth height at p (in cells): two travelling waves, some noise, and the pointer's ripple.
fn height(p: vec2f, ptr: vec2f) -> f32 {
  let t = params.time;
  var h = sin(p.x * 0.55 - t * 1.9 + sin(p.y * 0.4 + t * 0.6) * 1.3) * 0.55;
  h += sin(p.x * 1.1 + p.y * 0.5 - t * 2.7) * 0.2;
  h += simplex3d(vec3f(p * 0.35, t * 0.2)) * 0.35;
  let d = distance(p, ptr);
  h += sin(d * 2.4 - t * 7.0) * exp(-d * 0.55) * params.push * 0.7;
  return h;
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let scale = 1.0 / (CELL * params.pixelRatio);
  let p = uv * params.resolution * scale;
  let ptr = params.pointer * scale;

  let e = 0.04;
  let h = height(p, ptr);
  let hx = (height(p + vec2f(e, 0.0), ptr) - h) / e;
  let hy = (height(p + vec2f(0.0, e), ptr) - h) / e;
  let n = normalize(vec3f(-hx, -hy, 1.6));

  // The checks ride on the cloth: fold them by the slope.
  let w = p + vec2f(hx, hy) * 0.14 + vec2f(0.0, h * 0.2);
  let f = fract(w) - 0.5;
  let aa = fwidth(w.x) * 1.5;
  let sx = smoothstep(-aa, aa, f.x);
  let sy = smoothstep(-aa, aa, f.y);
  let checker = sx + sy - 2.0 * sx * sy; // XOR of the two half-planes, anti-aliased
  let parity = f32((i32(floor(w.x)) + i32(floor(w.y))) & 1);
  let light = mix(checker, 1.0 - checker, parity);
  let albedo = mix(0.004, 0.034, light);

  let l = normalize(vec3f(0.5, -0.6, 0.65));
  let diffuse = max(dot(n, l), 0.0);
  let v = vec3f(0.0, 0.0, 1.0);
  let spec = pow(max(dot(reflect(-l, n), v), 0.0), 36.0);

  // A volt sweep crosses every few seconds.
  let sweepX = fract(params.time * 0.07) * 2.2 - 0.6;
  let sweep = exp(-pow((uv.x - sweepX - uv.y * 0.25) * 4.0, 2.0));

  var color = vec3f(albedo) * (0.35 + diffuse * 1.1);
  color += mix(WHITE, VOLT, 0.6) * spec * (0.05 + sweep * 0.6);
  color += VOLT * sweep * 0.01 * (0.5 + light);

  var display = linearToSrgb3(tonemapAces(color * 1.2));
  // Fade in from the page at the top, and keep the left side dim under the copy.
  let page = linearToSrgb3(VOID);
  let show = smoothstep(0.08, 0.9, uv.y) * mix(0.45, 1.0, smoothstep(0.1, 0.75, uv.x));
  display = mix(page, display, show);
  return vec4f(display, 1.0);
}
