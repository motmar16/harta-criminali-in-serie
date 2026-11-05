import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre 6 caută worker-ul lângă bundle (./maplibre-gl-worker.mjs), fișier pe care Vite nu-l copiază.
// Îl împachetăm explicit ca worker ES și îi dăm URL-ul.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

maplibregl.setWorkerUrl(workerUrl);

// Basemap gratuit, fără cheie: OpenFreeMap (atribuire OSM inclusă în stil).
export const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';

export function createMap(container: HTMLElement): maplibregl.Map {
  const map = new maplibregl.Map({
    container,
    style: STYLE_URL,
    center: [10, 25],
    zoom: 1.6,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  return map;
}
