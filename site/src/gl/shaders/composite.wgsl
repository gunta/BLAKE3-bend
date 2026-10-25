// Final pass for the hero: scene plus two bloom bands, a touch of chromatic
// aberration toward the edges, ACES, grain and a vignette, then the sRGB
// transfer. The bottom edge fades into the page's own background, so the
// canvas has no seam where the next section starts.

import { linearToSrgb3, tonemapAces } from "@vgpu/wgsl-std/color";
import { hash2 } from "@vgpu/wgsl-std/hash";

struct Params {
  exposure: f32,
  bloomNear: f32,
  bloomFar: f32,
  aberration: f32,
  grain: f32,
  time: f32,
  fade: f32,
  pad: f32,
}

@group(0) @binding(0) var scene: texture_2d<f32>;
@group(0) @binding(1) var near: texture_2d<f32>;
@group(0) @binding(2) var far: texture_2d<f32>;
@group(0) @binding(3) var samp: sampler;
@group(0) @binding(4) var<uniform> params: Params;

// The page background (#060608), linear.
const VOID = vec3f(0.0018, 0.0018, 0.0025);

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let centered = uv - 0.5;
  let shift = centered * dot(centered, centered) * params.aberration;
  let r = textureSampleLevel(scene, samp, uv + shift, 0.0).r;
  let gb = textureSampleLevel(scene, samp, uv, 0.0).gb;
  let b = textureSampleLevel(scene, samp, uv - shift, 0.0).b;
  var color = vec3f(r, gb.x, mix(gb.y, b, 0.6));
  color += textureSampleLevel(near, samp, uv, 0.0).rgb * params.bloomNear;
  color += textureSampleLevel(far, samp, uv, 0.0).rgb * params.bloomFar;

  var display = linearToSrgb3(tonemapAces(max(color, vec3f(0.0)) * params.exposure));

  let vignette = smoothstep(1.15, 0.35, length(centered * vec2f(1.25, 1.0)));
  display *= mix(0.55, 1.0, vignette);

  let noise = hash2(floor(uv * 1400.0) + fract(params.time * 7.0) * 113.0).x - 0.5;
  display += noise * params.grain;

  let page = linearToSrgb3(VOID);
  display = mix(display, page, smoothstep(1.0 - params.fade, 1.0, uv.y));
  return vec4f(display, 1.0);
}
