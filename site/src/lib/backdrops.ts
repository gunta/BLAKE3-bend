/**
 * The site's background photographs, read from the pipeline's manifest at build
 * time (a glob, so a checkout without generated backgrounds still builds).
 */
import { getBackgroundPicture, type BackgroundManifest } from './backgrounds';
import { withBase } from './site';

const manifests = import.meta.glob<BackgroundManifest>('../../backgrounds/manifest.json', { eager: true, import: 'default' });

export const backdrop = (name: string) => getBackgroundPicture(Object.values(manifests)[0], name, withBase);

/** The hero photo's rendered width: a band under the header on tall screens, cover-cropped otherwise. */
export const HERO_SIZES = '(max-aspect-ratio: 23/20) max(100vw, 72svh + 7rem), (max-aspect-ratio: 16/9) 178svh, 100vw';
