// Bloom bright pass: keeps what is brighter than the threshold, with a soft
// knee. Rendering into a half-size target with a linear sampler is also the
// first downsample.

import { luminance } from "@vgpu/wgsl-std/color";

struct Bright {
  threshold: f32,
  knee: f32,
}

@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> bright: Bright;

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let color = textureSampleLevel(src, samp, uv, 0.0).rgb;
  let weight = smoothstep(bright.threshold, bright.threshold + bright.knee, luminance(color));
  return vec4f(color * weight, 1.0);
}
