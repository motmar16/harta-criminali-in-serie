// @ts-check
import { defineConfig } from 'astro/config';

// Site complet static (output implicit: 'static'). Datele vin din public/data/, generate de pipeline.
export default defineConfig({
  trailingSlash: 'ignore',
  vite: {
    // MapLibre 6 își încarcă worker-ul (ES module) relativ la import.meta.url;
    // pre-bundling-ul Vite din dev strică acele căi relative.
    optimizeDeps: { exclude: ['maplibre-gl'] },
    worker: { format: 'es' },
  },
});
