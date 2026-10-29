/**
 * BLAKE3's tree as SVG paths: 32 leaves merging over five levels into one
 * root. Drawn on the Open Graph card.
 */

/** Where each level starts along the tree, and how far its nodes spread. */
const U = [0, 0.34, 0.56, 0.71, 0.82, 0.9];
const S = [1, 0.8, 0.58, 0.38, 0.19, 0];

/** merge.wgsl staggers leaf starts with a hash; any stable spread reads the same. */
const stagger = (i: number) => (((Math.sin(i * 12.9898 + 4.1) * 43758.5453) % 1) + 1) % 1;

export interface TreeBox {
  /** Leaf start x, root x, centre y, half height (px). */
  x0: number;
  rootX: number;
  y: number;
  half: number;
}

export function treePaths(box: TreeBox): { edges: { d: string; level: number }[]; root: { x: number; y: number } } {
  const x1 = box.x0 + (box.rootX - box.x0) / U[5]!;
  const X = (u: number) => box.x0 + (x1 - box.x0) * u;
  const Y = (k: number, i: number) => box.y + (((i + 0.5) / (32 >> k)) * 2 - 1) * S[k]! * box.half;
  const f = (n: number) => n.toFixed(1);
  const edges: { d: string; level: number }[] = [];
  for (let k = 0; k < 5; k++) {
    for (let i = 0; i < 32 >> k; i++) {
      const xa = k === 0 ? X(stagger(i) * 0.24 - 0.06) : X(U[k]!);
      const xb = X(U[k + 1]!);
      const xe = X(U[k]! + (U[k + 1]! - U[k]!) * 0.42);
      const ya = Y(k, i);
      const yb = Y(k + 1, i >> 1);
      // smoothstep is the cubic Bezier whose control points sit at the ends' heights.
      const c1 = xe + (xb - xe) / 3;
      const c2 = xe + (2 * (xb - xe)) / 3;
      edges.push({ d: `M${f(xa)} ${f(ya)}H${f(xe)}C${f(c1)} ${f(ya)} ${f(c2)} ${f(yb)} ${f(xb)} ${f(yb)}`, level: k });
    }
  }
  return { edges, root: { x: box.rootX, y: box.y } };
}
