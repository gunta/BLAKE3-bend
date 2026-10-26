// The hero scene: BLAKE3's tree drawn in light, the logo at full size.
//
// 32 leaves of uneven length merge level by level into one root, the way a
// BLAKE3 hash folds 1 KiB chunks into parents and parents into one digest. Packets run down every
// edge, denser toward the root, where the work piles up. The root flares, and a
// beam carries the current digest's 256 bits off to the right as dashes. Each
// keystroke in the hash box sends a wave down the tree (`wave`), and the root
// kicks when it lands (`kick`). The pointer is a lens that bends the field.
//
// Writes linear HDR into an rgba16float target; bloom and tone mapping follow.

import { hash1, hash2 } from "@vgpu/wgsl-std/hash";
import { simplex3d } from "@vgpu/wgsl-std/noise/simplex";

struct Params {
  resolution: vec2f,
  pointer: vec2f,
  // x0, centre y, x1, half height of the tree's box, in pixels
  tree: vec4f,
  time: f32,
  intro: f32,
  kick: f32,
  speed: f32,
  lens: f32,
  lensRadius: f32,
  pixelRatio: f32,
  wave: f32,
  digestA: vec4u,
  digestB: vec4u,
}

@group(0) @binding(0) var<uniform> params: Params;

const LEAVES: u32 = 32u;
const ION = vec3f(0.06, 0.77, 1.0);
const VOLT = vec3f(0.66, 1.0, 0.04);
const WHITE = vec3f(1.0, 1.0, 0.92);
const VOID = vec3f(0.0018, 0.0018, 0.0025);

// Where each level starts along the tree (0 = leaves, 5 = root) ...
// (src/lib/tree.ts draws the same layout as SVG; keep the two in step.)
fn levelU(k: u32) -> f32 {
  let u = array<f32, 6>(0.0, 0.34, 0.56, 0.71, 0.82, 0.9);
  return u[min(k, 5u)];
}

// ... and how far its nodes spread: the tree narrows to a point.
fn levelS(k: u32) -> f32 {
  let s = array<f32, 6>(1.0, 0.8, 0.58, 0.38, 0.19, 0.0);
  return s[min(k, 5u)];
}

fn treeX(u: f32) -> f32 {
  return mix(params.tree.x, params.tree.z, u);
}

// Vertical position of node i on level k, in pixels. Nodes sway a little; less near the root.
fn nodeY(k: u32, i: u32) -> f32 {
  let n = f32(LEAVES >> k);
  let b = ((f32(i) + 0.5) / n) * 2.0 - 1.0;
  let s = levelS(k);
  let sway = 0.03 * s * sin(params.time * 0.55 + f32(i) * 1.7 + f32(k) * 2.3);
  return params.tree.y + (b * s + sway) * params.tree.w;
}

fn digestBit(index: u32) -> u32 {
  let word = (index >> 5u) & 7u;
  var w = params.digestA[word & 3u];
  if (word >= 4u) {
    w = params.digestB[word & 3u];
  }
  return (w >> (index & 31u)) & 1u;
}

struct EdgeHit {
  distance: f32,
  along: f32,
}

// Distance from p to edge (k, i): flat for the first 42%, then an eased turn into
// the parent, the logo's horizontal-then-diagonal stroke with its corners rounded.
fn edgeAt(p: vec2f, k: u32, i: u32) -> EdgeHit {
  let xa = treeX(levelU(k));
  let xb = treeX(levelU(k + 1u));
  let ya = nodeY(k, i);
  let yb = nodeY(k + 1u, i >> 1u);
  let t = clamp((p.x - xa) / (xb - xa), 0.0, 1.0);
  let e0 = 0.42;
  let x = clamp((t - e0) / (1.0 - e0), 0.0, 1.0);
  let s = x * x * (3.0 - 2.0 * x);
  let ds = 6.0 * x * (1.0 - x) / (1.0 - e0);
  let y = mix(ya, yb, s);
  let slope = (yb - ya) * ds / (xb - xa);
  return EdgeHit(abs(p.y - y) / sqrt(1.0 + slope * slope), t);
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let res = params.resolution;
  let pr = params.pixelRatio;
  let raw = uv * res;

  // The pointer lens: pixels near it read the field from closer in, so edges bulge around it.
  let toPointer = raw - params.pointer;
  let r = length(toPointer) / (params.lensRadius * pr);
  let p = raw - toPointer * params.lens * exp(-r * r);

  // Background: near-black with a slow, faint nebula in the brand colors.
  let q = raw / res.y;
  let n = simplex3d(vec3f(q * 1.4, params.time * 0.025)) * 0.5 + 0.5;
  var color = VOID + mix(ION, VOLT, n) * 0.0035 * n * n;

  let u = (p.x - params.tree.x) / (params.tree.z - params.tree.x);
  let reveal = params.intro * 1.25 - 0.1;
  let shown = 1.0 - smoothstep(reveal - 0.05, reveal, u);
  let front = exp(-abs(u - reveal) * 40.0) * (1.0 - smoothstep(0.85, 1.0, params.intro));

  // Edges: only the level under this pixel can be near it, and only the few
  // edges around the pixel's row within that level.
  let rootU = levelU(5u);
  if (u > -0.2 && u < rootU) {
    var k = 0u;
    for (var j = 1u; j < 5u; j++) {
      if (u >= levelU(j)) {
        k = j;
      }
    }
    let count = LEAVES >> k;
    let ua = levelU(k);
    let ub = levelU(k + 1u);
    let spread = max(mix(levelS(k), levelS(k + 1u), smoothstep(0.42, 1.0, clamp((u - ua) / (ub - ua), 0.0, 1.0))), 0.02);
    let guess = i32(floor(((((p.y - params.tree.y) / params.tree.w) / spread + 1.0) * 0.5) * f32(count)));
    let lo = u32(clamp(guess - 2, 0, i32(count) - 1));
    let hi = u32(clamp(guess + 2, 0, i32(count) - 1));

    let heat = smoothstep(0.1, 0.9, u);
    let base = mix(ION, VOLT, heat);
    let width = mix(0.7, 1.9, f32(k) / 4.0) * pr;

    for (var i = lo; i <= hi; i++) {
      let hit = edgeAt(p, k, i);
      var line = exp(-(hit.distance * hit.distance) / (width * width));
      let glow = exp(-hit.distance / (5.0 * pr)) * 0.12;
      // Leaves start at uneven points, like the speed lines in the mark.
      if (k == 0u) {
        let start = hash1(f32(i) * 3.7 + 1.0) * 0.24 - 0.06;
        let enter = smoothstep(start, start + 0.08, u);
        line *= enter;
        if (u < start) {
          continue;
        }
      }
      // Packets: comets running toward the root, more of them on deeper levels.
      let id = f32(k * 64u + i);
      let density = 5.0 + f32(k) * 3.5;
      let phase = q.x * density - params.time * params.speed * (0.9 + 0.35 * f32(k)) + hash1(id * 1.93) * 7.0;
      let cell = floor(phase);
      let lit = step(0.62 - f32(k) * 0.14, hash1(cell * 0.71 + id * 13.1));
      let tail = 1.0 - fract(phase);
      let comet = exp(-tail * 10.0) * lit * (1.0 - smoothstep(0.985, 1.0, fract(phase)));
      let wave = exp(-abs(u - params.wave) * 22.0) * step(params.wave, 1.2);
      let energy = mix(0.16, 0.7, heat) + comet * 3.2 + wave * 4.0 + front * 2.5;
      let tint = mix(base, WHITE, clamp(comet * 0.6 + wave * 0.5, 0.0, 0.85));
      color += tint * (line * energy + glow * mix(0.4, 1.0, heat)) * shown;
    }
  }

  // The root and its flare.
  let ignite = smoothstep(0.78, 1.0, params.intro);
  let root = vec2f(treeX(rootU), params.tree.y);
  let dr = (p - root) / res.y;
  let rr = dot(dr, dr);
  let breathe = 0.85 + 0.15 * sin(params.time * 2.1);
  let energy = ignite * (breathe + params.kick * 2.6);
  color += WHITE * exp(-rr * 9000.0) * 6.0 * energy;
  color += mix(VOLT, WHITE, 0.35) * exp(-rr * 900.0) * 0.9 * energy;
  color += VOLT * 0.06 / (1.0 + rr * 600.0) * energy;
  color += mix(VOLT, WHITE, 0.5) * exp(-abs(dr.y) * 1100.0) * exp(-abs(dr.x) * 4.5) * 0.5 * energy;
  color += VOLT * exp(-abs(dr.x) * 1100.0) * exp(-abs(dr.y) * 16.0) * 0.12 * energy;

  // The beam: the digest's 256 bits as dashes, streaming out of the root.
  if (p.x > root.x) {
    let dy = (p.y - root.y);
    let bw = 1.5 * pr;
    let core = exp(-(dy * dy) / (bw * bw));
    let s = (p.x - root.x) / (9.0 * pr) - params.time * params.speed * 26.0;
    let f = fract(s);
    let index = u32(i32(floor(s)) & 255);
    let bit = f32(digestBit(index));
    let dash = smoothstep(0.0, 0.12, f) * (1.0 - smoothstep(0.6, 0.74, f));
    let fade = exp(-(p.x - root.x) / res.x * 2.2);
    let intensity = (0.25 + dash * mix(0.4, 3.2, bit)) * fade * ignite * (1.0 + params.kick * 1.5);
    color += mix(VOLT, WHITE, 0.25 + 0.5 * bit * dash) * core * intensity;
    color += VOLT * exp(-abs(dy) / (7.0 * pr)) * 0.05 * fade * ignite;
  }

  // A soft volt halo where the pointer bends the field.
  color += VOLT * exp(-r * r * 3.0) * 0.012 * params.lens;

  return vec4f(color, 1.0);
}
