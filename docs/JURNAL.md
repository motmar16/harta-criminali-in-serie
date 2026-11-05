# Jurnal

## 2026-11-05 — Faza 0: schelet

- Repo git inițializat pe `main`; structura din secțiunea 4.3 a planului (module încă neimplementate pentru fazele 2–3 au doar docstring).
- Stack instalat: Python 3.12.10 (venv `.venv/`), Astro 7.4.5, MapLibre GL JS 6.16.0, basemap OpenFreeMap `positron`.
- Abatere: MapLibre 6 nu mai are export implicit, deci `import * as maplibregl from 'maplibre-gl'`.
- Abatere: `npm run dev` funcționează din rădăcină (package.json care deleagă la `site/`) și din `site/`.
- Deciziile D1–D6 au fost puse lui Marius; până la răspuns se folosesc valorile implicite din plan.
  Emailul lui Marius NU e pus în User-Agent; contactul se poate seta cu `HARTA_CONTACT`.
- Abatere: MapLibre 6 își caută worker-ul lângă bundle; în build Vite nu-l copiază, iar în dev pre-bundling-ul îi strică căile.
  Rezolvare: `optimizeDeps.exclude: ['maplibre-gl']`, `worker.format: 'es'` și `setWorkerUrl()` cu worker-ul importat prin `?worker&url`.
- Acceptare faza 0: `npm run dev` afișează harta lumii (verificat în browser, dev și `astro preview`); `python -m pipeline --help` răspunde.
