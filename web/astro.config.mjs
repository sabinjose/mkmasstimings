import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://mkmasstimings.pages.dev',
  vite: {
    plugins: [tailwindcss()],
  },
  build: {
    // Inline CSS into the HTML so first paint already has every rule.
    // Without this the page renders unstyled briefly on cold loads
    // ("vibrates" while the external CSS streams in).
    inlineStylesheets: 'always',
  },
});
