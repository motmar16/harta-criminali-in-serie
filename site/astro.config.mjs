// @ts-check
import { defineConfig } from 'astro/config';

// Site complet static (output implicit: 'static'). Datele vin din public/data/, generate de pipeline.
export default defineConfig({
  // GitHub Pages: SITE_URL=https://motmar16.github.io, SITE_BASE=/harta-criminali-in-serie (setate în workflow).
  // Cu domeniu propriu: SITE_BASE nesetat (rădăcina).
  site: process.env.SITE_URL || undefined,
  base: process.env.SITE_BASE || '/',
  trailingSlash: 'ignore',
  vite: {
    // MapLibre 6 își încarcă worker-ul (ES module) relativ la import.meta.url;
    // pre-bundling-ul Vite din dev strică acele căi relative.
    optimizeDeps: { exclude: ['maplibre-gl'] },
    worker: { format: 'es' },
  },
});
