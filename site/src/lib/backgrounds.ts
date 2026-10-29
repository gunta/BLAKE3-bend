/** The public export subset of the background pipeline's manifest. */
export interface BackgroundManifest {
  slots: {
    slot: string;
    exports: {
      path: string;
      format: string;
      dimensions: [number, number];
      verified: boolean;
    }[];
  }[];
}

/** Describe existing files only; no image transformation is needed. */
export function getBackgroundPicture(
  manifest: BackgroundManifest | undefined,
  name: string,
  withBase: (path: string) => string,
) {
  const slot = manifest?.slots.find((entry) => entry.slot === name);
  if (!slot) return undefined;
  const exports = slot.exports.filter((entry) => entry.verified);
  const sources = ['avif', 'jxl', 'webp'].flatMap((format) => {
    const renditions = exports
      .filter((entry) => entry.format === format)
      .sort((a, b) => a.dimensions[0] - b.dimensions[0]);
    return renditions.length ? [{
      type: `image/${format}`,
      srcset: renditions.map((entry) => `${withBase(entry.path.replace(/^public\//, ''))} ${entry.dimensions[0]}w`).join(', '),
    }] : [];
  });
  const largest = exports.filter((entry) => entry.format === 'webp')
    .sort((a, b) => b.dimensions[0] - a.dimensions[0])[0];
  const webp = sources.find((source) => source.type === 'image/webp');
  if (!largest || !webp) return undefined;
  return {
    sources,
    fallback: {
      src: withBase(largest.path.replace(/^public\//, '')),
      srcset: webp.srcset,
      width: largest.dimensions[0],
      height: largest.dimensions[1],
    },
  };
}
