import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getBackgroundPicture, type BackgroundManifest } from '../src/lib/backgrounds.ts';

const manifest: BackgroundManifest = {
  slots: [{
    slot: 'hero',
    exports: [3200, 960, 1600].flatMap((width) =>
      (['webp', 'jxl', 'avif'] as const).map((format) => ({
        path: `public/backgrounds/hero-${width}.${format}`,
        format,
        dimensions: [width, width * 9 / 16] as [number, number],
        verified: true,
      })),
    ),
  }],
};
const withBase = (path: string) => `/turboblake/${path}`;

test('allows the legacy image branch when the manifest or slot is absent', () => {
  assert.equal(getBackgroundPicture(undefined, 'hero', withBase), undefined);
  assert.equal(getBackgroundPicture(manifest, 'missing', withBase), undefined);
});

test('omits unavailable codecs and refuses unverified WebP fallbacks', () => {
  const partial: BackgroundManifest = {
    slots: [{ slot: 'hero', exports: [
      { path: 'public/backgrounds/hero-960.webp', format: 'webp', dimensions: [960, 540], verified: true },
      { path: 'public/backgrounds/hero-3200.webp', format: 'webp', dimensions: [3200, 1800], verified: false },
    ] }],
  };
  const picture = getBackgroundPicture(partial, 'hero', (path) => `/${path}`);
  assert.deepEqual(picture?.sources, [{ type: 'image/webp', srcset: '/backgrounds/hero-960.webp 960w' }]);
  assert.equal(picture?.fallback.src, '/backgrounds/hero-960.webp');
  assert.equal(getBackgroundPicture({ slots: [{ slot: 'hero', exports: [] }] }, 'hero', withBase), undefined);
  assert.equal(getBackgroundPicture({ slots: [{ slot: 'hero', exports: manifest.slots[0]!.exports.filter((entry) => entry.format !== 'webp') }] }, 'hero', withBase), undefined);
});

test('uses ordered responsive preencoded sources and a WebP fallback under the site base', () => {
  const picture = getBackgroundPicture(manifest, 'hero', withBase);
  assert.ok(picture);
  assert.deepEqual(picture.sources.map((source) => source.type), ['image/avif', 'image/jxl', 'image/webp']);
  for (const [index, format] of ['avif', 'jxl', 'webp'].entries()) {
    assert.equal(picture.sources[index]?.srcset,
      [960, 1600, 3200].map((width) => `/turboblake/backgrounds/hero-${width}.${format} ${width}w`).join(', '));
  }
  assert.deepEqual(picture.fallback, {
    src: '/turboblake/backgrounds/hero-3200.webp',
    srcset: picture.sources[2]?.srcset,
    width: 3200,
    height: 1800,
  });
});
