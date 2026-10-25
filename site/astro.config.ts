import { defineConfig } from 'astro/config';

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
  devToolbar: {
    enabled: false,
  },
});
