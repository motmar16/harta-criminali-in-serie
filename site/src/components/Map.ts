import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre 6 caută worker-ul lângă bundle (./maplibre-gl-worker.mjs), fișier pe care Vite nu-l copiază.
// Îl împachetăm explicit ca worker ES și îi dăm URL-ul.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Feature, FeatureCollection, Point } from 'geojson';

maplibregl.setWorkerUrl(workerUrl);

// Basemap gratuit, fără cheie: OpenFreeMap (atribuire OSM inclusă în stil).
export const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
const DATA = '/data';

export interface Killer {
  id: string;
  slug: string;
  names: { primary: string; aliases: string[] };
  description: string | null;
  sex: string | null;
  birth: { date: string | null; place_id: string | null } | null;
  death: { date: string | null; place_id: string | null; cause: string | null } | null;
  countries: string[];
  active: { start: string; end: string } | null;
  victims: { proven: number | null; possible: number | null; note: string | null } | null;
  status: string | null;
  legal_status: string | null;
  penalty: string | null;
  summary: { text: string; license: string; source_url: string; attribution: string } | null;
  links: Record<string, string | null>;
  lists: string[];
  sources: Record<string, string | null>;
}

type EventProps = {
  id: string; killer_id: string; kind: string; place_name: string; precision: string;
  date: { start: string } | null; source_url: string; extraction: string; confidence: number;
};

const esc = (s: unknown): string =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const KIND_LABEL: Record<string, string> = { active_area: 'Area of activity', birth: 'Born', death: 'Died' };
const KIND_COLOR: Record<string, string> = { active_area: '#b35c1e', birth: '#2f6f9f', death: '#555a66' };
const PRECISION_LABEL: Record<string, string> = {
  address: 'address', city: 'city', county: 'county / district', admin1: 'state / region', country: 'country only',
};
const BASIS_LABEL: Record<string, string> = {
  'wikipedia-infobox': 'Wikipedia infobox',
  'wikipedia-lead': 'places linked in the Wikipedia introduction',
  'wikipedia-list': 'Wikipedia list of serial killers (country only)',
  'wikidata-citizenship': 'citizenship on Wikidata (country only, approximate)',
  'wikidata-P19': 'Wikidata (place of birth)',
  'wikidata-P20': 'Wikidata (place of death)',
};
const LEGAL_LABEL: Record<string, string> = {
  convicted: 'Convicted',
  unidentified: 'Unidentified perpetrator',
  suspected: 'Suspected / alleged — not convicted',
  acquitted: 'Acquitted',
  deceased_before_trial: 'Died before trial',
};

let killersById: Map<string, Killer> | null = null;
let eventsByKiller: Map<string, Feature<Point, EventProps>[]> | null = null;

async function loadDetails(): Promise<void> {
  if (killersById && eventsByKiller) return;
  const [ks, evs] = await Promise.all([
    fetch(`${DATA}/killers.json`).then((r) => r.json() as Promise<Killer[]>),
    fetch(`${DATA}/events.geojson`).then((r) => r.json() as Promise<FeatureCollection<Point, EventProps>>),
  ]);
  killersById = new Map(ks.map((k) => [k.id, k]));
  eventsByKiller = new Map();
  for (const f of evs.features) {
    const list = eventsByKiller.get(f.properties.killer_id) ?? [];
    list.push(f);
    eventsByKiller.set(f.properties.killer_id, list);
  }
}

function fmtVictims(v: Killer['victims']): string {
  if (!v || v.proven == null) return 'unknown';
  return v.possible ? `${v.proven}–${v.possible}` : String(v.proven);
}

function renderPanel(k: Killer, events: Feature<Point, EventProps>[]): string {
  const area = events.filter((e) => e.properties.kind === 'active_area');
  const others = events.filter((e) => e.properties.kind !== 'active_area');
  const areaBasis = k.sources.active_area ?? 'none';
  const legal = k.legal_status ? LEGAL_LABEL[k.legal_status] ?? k.legal_status : 'Legal status not verified';
  const suspected = k.legal_status === 'suspected' || k.legal_status === 'unidentified';
  const areaNames = area.map((e) => e.properties.place_name).join(', ') || 'unknown';
  const row = (label: string, value: string) => (value ? `<dt>${esc(label)}</dt><dd>${value}</dd>` : '');
  const life = [k.birth?.date && `b. ${esc(k.birth.date)}`, k.death?.date && `d. ${esc(k.death.date)}`]
    .filter(Boolean).join(' · ');
  return `
    <header>
      <h2>${esc(k.names.primary)}</h2>
      ${k.description ? `<p class="desc">${esc(k.description)}</p>` : ''}
      ${k.names.aliases.length ? `<p class="aliases">Also known as: ${esc(k.names.aliases.join('; '))}</p>` : ''}
    </header>
    <p class="legal ${suspected ? 'warn' : ''}">${esc(legal)}</p>
    <dl>
      ${row('Life', life)}
      ${row('Active', k.active ? `${esc(k.active.start)}${k.active.end !== k.active.start ? '–' + esc(k.active.end) : ''}` : '')}
      ${row('Victims', k.victims ? `${esc(fmtVictims(k.victims))}${k.victims.note && k.victims.note.replace(/\s/g, '') !== fmtVictims(k.victims) && k.victims.note !== String(k.victims.proven) ? ` <span class="muted">(“${esc(k.victims.note)}”)</span>` : ''}` : '')}
      ${row('Countries', k.countries.map((c) => `<a href="/country/${esc(c.toLowerCase())}">${esc(c)}</a>`).join(', '))}
      ${row('Penalty', k.penalty ? esc(k.penalty) : '')}
    </dl>
    <section>
      <h3>Locations</h3>
      <p class="note">Individual murder locations are not yet documented in our data. Area of activity: <strong>${esc(areaNames)}</strong>
      <span class="muted">(source: ${esc(BASIS_LABEL[areaBasis] ?? areaBasis)})</span>.</p>
      <ol class="events">
        ${[...area, ...others].map((e) => `
          <li><span class="dot" style="background:${KIND_COLOR[e.properties.kind] ?? '#666'}"></span>
            <strong>${esc(KIND_LABEL[e.properties.kind] ?? e.properties.kind)}</strong>: ${esc(e.properties.place_name)}
            ${e.properties.date ? ` <span class="muted">${esc(e.properties.date.start)}</span>` : ''}
            <span class="muted">· precision: ${esc(PRECISION_LABEL[e.properties.precision] ?? e.properties.precision)}</span>
            · <a href="${esc(e.properties.source_url)}" target="_blank" rel="noopener">source</a></li>`).join('')}
      </ol>
    </section>
    ${k.summary ? `<section><h3>Summary</h3><p class="summary">${esc(k.summary.text)}</p>
      <p class="muted small">Text from ${esc(k.summary.attribution)}, <a href="${esc(k.summary.source_url)}" target="_blank" rel="noopener">this revision</a>,
      licensed <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>.</p></section>` : ''}
    <section>
      <h3>Sources</h3>
      <ul class="links">
        ${k.links.wikipedia ? `<li><a href="${esc(k.links.wikipedia)}" target="_blank" rel="noopener">Wikipedia</a></li>` : ''}
        ${k.links.wikidata ? `<li><a href="${esc(k.links.wikidata)}" target="_blank" rel="noopener">Wikidata ${esc(k.id)}</a></li>` : ''}
      </ul>
      ${k.lists.length ? `<p class="muted small">Listed in: ${esc(k.lists.join('; '))}</p>` : ''}
    </section>`;
}

export function createMap(container: HTMLElement): maplibregl.Map {
  const map = new maplibregl.Map({
    container,
    style: STYLE_URL,
    center: [10, 25],
    zoom: 1.6,
    attributionControl: { compact: true, customAttribution: 'Data: <a href="https://www.wikidata.org">Wikidata</a> (CC0), <a href="https://en.wikipedia.org">Wikipedia</a> (CC BY-SA)' },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  return map;
}

export function initKillerMap(container: HTMLElement, panel: HTMLElement): void {
  const map = createMap(container);
  const params = new URLSearchParams(location.search);
  const countryFilter = params.get('c')?.toUpperCase() ?? null;

  map.on('load', async () => {
    const index = (await fetch(`${DATA}/killers-index.geojson`).then((r) => r.json())) as FeatureCollection<Point>;
    if (countryFilter) {
      index.features = index.features.filter((f) => String(f.properties?.countries ?? '').split(',').includes(countryFilter));
      if (index.features.length) {
        const b = new maplibregl.LngLatBounds();
        index.features.forEach((f) => b.extend(f.geometry.coordinates as [number, number]));
        map.fitBounds(b, { padding: 60, maxZoom: 7, duration: 0 });
      }
    }
    map.addSource('killers', { type: 'geojson', data: index, cluster: true, clusterRadius: 42, clusterMaxZoom: 10 });
    map.addSource('selected', { type: 'geojson', data: EMPTY });

    map.addLayer({
      id: 'clusters', type: 'circle', source: 'killers', filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#3b5b7a', 'circle-opacity': 0.82, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.2,
        'circle-radius': ['step', ['get', 'point_count'], 13, 10, 17, 50, 22, 200, 28],
      },
    });
    map.addLayer({
      id: 'cluster-count', type: 'symbol', source: 'killers', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Regular'], 'text-size': 12 },
      paint: { 'text-color': '#ffffff' },
    });
    map.addLayer({
      id: 'killer-points', type: 'circle', source: 'killers', filter: ['!', ['has', 'point_count']],
      paint: {
        // precizie slabă (stat/țară) = cerc mai mare și mai transparent
        'circle-radius': ['match', ['get', 'precision'], 'country', 9, 'admin1', 7.5, 5.5],
        'circle-color': ['match', ['get', 'legal'], 'suspected', '#8a8f99', 'unidentified', '#8a8f99', '#3b5b7a'],
        'circle-opacity': ['match', ['get', 'precision'], 'country', 0.35, 'admin1', 0.55, 0.9],
        'circle-stroke-color': '#fff', 'circle-stroke-width': 1,
      },
    });
    map.addLayer({
      id: 'selected-points', type: 'circle', source: 'selected',
      paint: {
        'circle-radius': 7,
        'circle-color': ['match', ['get', 'kind'], 'birth', KIND_COLOR.birth, 'death', KIND_COLOR.death, KIND_COLOR.active_area],
        'circle-stroke-color': '#fff', 'circle-stroke-width': 2,
      },
    });
    map.addLayer({
      id: 'selected-labels', type: 'symbol', source: 'selected',
      layout: {
        'text-field': ['concat', ['match', ['get', 'kind'], 'birth', 'Born: ', 'death', 'Died: ', ''], ['get', 'place_name']],
        'text-font': ['Noto Sans Regular'], 'text-size': 12, 'text-offset': [0, 1.2], 'text-anchor': 'top',
      },
      paint: { 'text-color': '#222', 'text-halo-color': '#fff', 'text-halo-width': 1.5 },
    });

    map.on('click', 'clusters', async (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const src = map.getSource('killers') as maplibregl.GeoJSONSource;
      const zoom = await src.getClusterExpansionZoom(f.properties.cluster_id as number);
      map.easeTo({ center: (f.geometry as Point).coordinates as [number, number], zoom });
    });
    map.on('click', 'killer-points', (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) void select(id);
    });
    for (const layer of ['clusters', 'killer-points']) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''));
    }
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on('mousemove', 'killer-points', (e) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      popup.setLngLat(e.lngLat).setHTML(`<strong>${esc(p.name)}</strong><br><span class="muted">${esc(p.place)}</span>`).addTo(map);
    });
    map.on('mouseleave', 'killer-points', () => popup.remove());

    const initial = params.get('k');
    if (initial) void select(initial);
  });

  async function select(id: string): Promise<void> {
    panel.hidden = false;
    panel.querySelector('.panel-body')!.innerHTML = '<p class="muted">Loading…</p>';
    await loadDetails();
    const k = killersById!.get(id);
    if (!k) {
      panel.querySelector('.panel-body')!.innerHTML = '<p>Not found.</p>';
      return;
    }
    const evs = eventsByKiller!.get(id) ?? [];
    panel.querySelector('.panel-body')!.innerHTML = renderPanel(k, evs);
    (map.getSource('selected') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: evs });
    if (evs.length) {
      const b = new maplibregl.LngLatBounds();
      evs.forEach((f) => b.extend(f.geometry.coordinates as [number, number]));
      map.fitBounds(b, { padding: { top: 80, bottom: 80, left: 80, right: Math.min(460, innerWidth * 0.45) }, maxZoom: 7 });
    }
    const url = new URL(location.href);
    url.searchParams.set('k', id);
    history.replaceState(null, '', url);
  }

  panel.querySelector('.close')?.addEventListener('click', () => {
    panel.hidden = true;
    (map.getSource('selected') as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY);
    const url = new URL(location.href);
    url.searchParams.delete('k');
    history.replaceState(null, '', url);
  });
}
