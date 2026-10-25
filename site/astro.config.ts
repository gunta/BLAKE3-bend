import { defineConfig } from 'astro/config';
import { wgslVitePlugin } from '@vgpu/wgsl/loader-vite';

// GitHub Pages project site: https://gunta.github.io/BLAKE3-bend/
// Every internal URL goes through `withBase` (src/lib/site.ts) so it carries `base`.
export default defineConfig({
  site: 'https://gunta.github.io',
  base: '/BLAKE3-bend',
  output: 'static',
  build: {
    // One small page: inline the CSS so the first paint needs a single request.
    inlineStylesheets: 'always',
  },
  vite: {
    // .wgsl imports are resolved and prepared at build time, so the browser
    // never loads the WGSL parser (https://vgpu.sh/docs/get-started/web).
    plugins: [wgslVitePlugin()],
  },
  devToolbar: {
    enabled: false,
  },
});
