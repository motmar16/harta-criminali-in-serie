import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre 6 caută worker-ul lângă bundle (./maplibre-gl-worker.mjs), fișier pe care Vite nu-l copiază.
// Îl împachetăm explicit ca worker ES și îi dăm URL-ul.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Feature, FeatureCollection, Point } from 'geojson';

maplibregl.setWorkerUrl(workerUrl);

// Basemap gratuit, fără cheie: OpenFreeMap (atribuire OSM inclusă în stil).
const STYLES = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
};
const DATA = '/data';
const RADFORD_URL = 'https://maamodt.asp.radford.edu/Psyc%20405/serial_killer_timelines.htm';

// ------------------------------------------------------------------ tipuri

export interface Killer {
  id: string;
  slug: string;
  names: { primary: string; aliases: string[] };
  description: string | null;
  sex: string | null;
  type?: string[];
  birth: { date: string | null; place_id: string | null } | null;
  death: { date: string | null; place_id: string | null; cause: string | null } | null;
  countries: string[];
  active: { start: string; end: string } | null;
  victims: { proven: number | null; possible: number | null; note: string | null } | null;
  status: string | null;
  legal_status: string | null;
  penalty: string | null;
  method: string[];
  victim_types: string[];
  classification: string[];
  summary: { text: string; license: string; source_url: string; attribution: string } | null;
  image: { thumb: string; page: string; license: string; credit: string } | null;
  links: Record<string, string | null>;
  lists: string[];
  sources: Record<string, string | null>;
  murderpedia?: { url: string; classification: string | null; method: string | null; location: string | null } | null;
}

type IndexProps = {
  id: string; slug: string; name: string; countries: string; victims: number | null; legal: string | null;
  precision: string; place: string; sex: string | null; from: number | null; to: number | null;
  m: string; vt: string; img: 0 | 1; type: string;
};
type EventProps = {
  id: string; killer_id: string; kind: string; place_name: string; precision: string;
  date: { start: string } | null; source_url: string; extraction: string; confidence: number;
};

export interface Filters {
  q: string;
  type: '' | 'serial_killer' | 'spree_killer' | 'mass_murderer';
  sex: '' | 'male' | 'female';
  from: number | null;
  to: number | null;
  minVictims: number;
  legal: Set<string>;
  methods: Set<string>;
  victimTypes: Set<string>;
  cityOnly: boolean;
  withPhoto: boolean;
  country: string | null;
}

// ------------------------------------------------------------------ etichete

const esc = (s: unknown): string =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const KIND_LABEL: Record<string, string> = { active_area: 'Area of activity', birth: 'Born', death: 'Died' };
const PRECISION_LABEL: Record<string, string> = {
  address: 'exact place', city: 'city', county: 'county / district', admin1: 'state / region', country: 'country only',
};
const BASIS_LABEL: Record<string, string> = {
  'wikipedia-infobox': 'Wikipedia infobox',
  'wikipedia-lead': 'places linked in the Wikipedia introduction',
  'wikipedia-crime-sentences': 'places linked in sentences about the crimes (Wikipedia)',
  'wikipedia-crime-sections': 'places linked in the crimes section of the Wikipedia article',
  'wikipedia-body': 'places linked in the Wikipedia article',
  'wikipedia-list': 'Wikipedia list of serial killers (country only)',
  'wikidata-citizenship': 'citizenship on Wikidata (country only, approximate)',
  murderpedia: 'Murderpedia “Location” field',
  radford: 'Radford University timeline (crime entries)',
  'wikipedia-other-languages': 'places linked in sentences about the crimes (Wikipedia in other languages)',
  'wikipedia-list-text': 'places linked in the Wikipedia list entry',
  manual: 'manual correction',
  'wikidata-P19': 'Wikidata (place of birth)',
  'wikidata-P20': 'Wikidata (place of death)',
};
export const LEGAL_LABEL: Record<string, string> = {
  convicted: 'Convicted',
  unidentified: 'Unidentified perpetrator',
  suspected: 'Suspected / alleged — not convicted',
  acquitted: 'Acquitted',
  deceased_before_trial: 'Died before trial',
};

// culori stabile în ambele teme
const SEX_COLOR = { male: '#4f7cac', female: '#d08a2e', other: '#8b8f98' };
const SPREE_COLOR = '#8e4fb3';
const MASS_COLOR = '#23877d';
const TYPE_LABEL: Record<string, string> = {
  serial_killer: 'Serial killer', spree_killer: 'Spree killer', mass_murderer: 'Mass murderer',
};
const KIND_COLOR: Record<string, string> = { active_area: '#c0563b', birth: '#3f8f7a', death: '#7a7f8c' };

// ------------------------------------------------------------------ date

let index: Feature<Point, IndexProps>[] = [];
let killersById: Map<string, Killer> | null = null;
let eventsByKiller: Map<string, Feature<Point, EventProps>[]> | null = null;
let areaEvents: FeatureCollection<Point, EventProps> | null = null;

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
  areaEvents = { type: 'FeatureCollection', features: evs.features.filter((f) => f.properties.kind === 'active_area') };
}

export function matches(p: IndexProps, f: Filters): boolean {
  if (f.q && !p.name.toLowerCase().includes(f.q.toLowerCase())) return false;
  if (f.sex && p.sex !== f.sex) return false;
  if (f.type && !(p.type || 'serial_killer').split(',').includes(f.type)) return false;
  if (f.from != null && (p.to ?? p.from ?? -1e9) < f.from) return false;
  if (f.to != null && (p.from ?? p.to ?? 1e9) > f.to) return false;
  if (f.minVictims > 0 && (p.victims ?? 0) < f.minVictims) return false;
  if (f.legal.size && !f.legal.has(p.legal ?? 'undetermined')) return false;
  if (f.methods.size) {
    const ms = p.m ? p.m.split(',') : [];
    if (![...f.methods].some((m) => ms.includes(m))) return false;
  }
  if (f.victimTypes.size) {
    const vs = p.vt ? p.vt.split(',') : [];
    if (![...f.victimTypes].some((v) => vs.includes(v))) return false;
  }
  if (f.cityOnly && !['address', 'city', 'county'].includes(p.precision)) return false;
  if (f.withPhoto && !p.img) return false;
  if (f.country && !p.countries.split(',').includes(f.country)) return false;
  return true;
}

// ------------------------------------------------------------------ panou

function fmtVictims(v: Killer['victims']): string {
  if (!v || v.proven == null) return 'unknown';
  return v.possible ? `${v.proven}–${v.possible}` : String(v.proven);
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function renderPanel(k: Killer, events: Feature<Point, EventProps>[]): string {
  const area = events.filter((e) => e.properties.kind === 'active_area');
  const others = events.filter((e) => e.properties.kind !== 'active_area');
  const areaBasis = k.sources.active_area ?? 'none';
  const legal = k.legal_status ? LEGAL_LABEL[k.legal_status] ?? k.legal_status : 'Legal status not verified';
  const suspected = k.legal_status === 'suspected' || k.legal_status === 'unidentified' || !k.legal_status;
  const areaNames = area.map((e) => e.properties.place_name).join(', ') || 'unknown';
  const row = (label: string, value: string) => (value ? `<dt>${esc(label)}</dt><dd>${value}</dd>` : '');
  const life = [k.birth?.date && `born ${esc(k.birth.date)}`, k.death?.date && `died ${esc(k.death.date)}`]
    .filter(Boolean).join(' · ');
  const showNote = k.victims?.note && k.victims.note.replace(/\s/g, '') !== fmtVictims(k.victims) &&
    k.victims.note !== String(k.victims.proven);
  const tags = (xs: string[] | undefined) => (xs ?? []).map((x) => `<span class="tag">${esc(cap(x))}</span>`).join(' ');
  const mp = k.murderpedia;
  return `
    ${k.image ? `<figure class="portrait">
        <img src="${esc(k.image.thumb)}" alt="${esc(k.names.primary)}" loading="lazy" referrerpolicy="no-referrer">
        <figcaption>${esc(k.image.credit)} · <a href="${esc(k.image.page)}" target="_blank" rel="noopener">${esc(k.image.license)}</a>, via Wikimedia Commons</figcaption>
      </figure>` : ''}
    <header class="ph">
      <h2>${esc(k.names.primary)}</h2>
      ${k.description ? `<p class="desc">${esc(cap(k.description))}</p>` : ''}
      ${k.names.aliases.length ? `<p class="aliases">Also known as ${esc(k.names.aliases.join(' · '))}</p>` : ''}
      <span class="legal ${suspected ? 'warn' : ''}">${esc(legal)}</span>
    </header>
    <dl class="facts">
      ${row('Life', life)}
      ${row('Active', k.active ? `${esc(k.active.start)}${k.active.end !== k.active.start ? '–' + esc(k.active.end) : ''}` : '')}
      ${row('Victims', k.victims ? `<strong>${esc(fmtVictims(k.victims))}</strong>${showNote ? ` <span class="muted">“${esc(k.victims!.note)}”</span>` : ''}` : '')}
      ${row('Countries', k.countries.map((c) => `<a href="/country/${esc(c.toLowerCase())}">${esc(c)}</a>`).join(', '))}
      ${row('Type', (k.type ?? ['serial_killer']).map((t) => TYPE_LABEL[t] ?? t).join(', '))}
      ${row('Classification', k.classification?.length ? esc(k.classification.join(', ')) + ' <span class="muted small">(Murderpedia)</span>' : '')}
      ${row('Method', tags(k.method))}
      ${row('Victims were', tags(k.victim_types))}
      ${row('Penalty', k.penalty ? esc(k.penalty) : '')}
    </dl>
    <section>
      <h3>Locations</h3>
      ${area[0]?.properties.precision === 'country' ? '<p class="note warnline">Only the country is known; the dot is placed near its centre, not at the crime scenes.</p>' : ''}
      <p class="note">Individual crime locations are not yet mapped. Area of activity${area.length >= 3 ? ' (shaded on the map)' : ''}: <strong>${esc(areaNames)}</strong>
      <span class="muted">— from ${esc(BASIS_LABEL[areaBasis] ?? areaBasis)}.</span></p>
      <ol class="events">
        ${[...area, ...others].map((e) => `
          <li><span class="dot" style="background:${KIND_COLOR[e.properties.kind] ?? '#666'}"></span>
            <span><strong>${esc(KIND_LABEL[e.properties.kind] ?? e.properties.kind)}</strong> · ${esc(e.properties.place_name)}
            ${e.properties.date ? ` <span class="muted">${esc(e.properties.date.start)}</span>` : ''}
            <br><span class="muted small">${esc(PRECISION_LABEL[e.properties.precision] ?? e.properties.precision)} ·
            <a href="${esc(e.properties.source_url)}" target="_blank" rel="noopener">source</a></span></span></li>`).join('')}
      </ol>
    </section>
    ${k.summary ? `<section><h3>Summary</h3><p class="summary">${esc(k.summary.text)}</p>
      <p class="muted small">From ${esc(k.summary.attribution)} (<a href="${esc(k.summary.source_url)}" target="_blank" rel="noopener">revision</a>),
      <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>.</p></section>` : ''}
    <section>
      <h3>Sources</h3>
      <ul class="sources">
        ${k.links.wikipedia ? `<li><a href="${esc(k.links.wikipedia)}" target="_blank" rel="noopener">Wikipedia</a> <span class="muted small">biography, infobox</span></li>` : ''}
        ${k.links.wikidata ? `<li><a href="${esc(k.links.wikidata)}" target="_blank" rel="noopener">Wikidata ${esc(k.id)}</a> <span class="muted small">dates, places</span></li>` : ''}
        ${mp ? `<li><a href="${esc(mp.url)}" target="_blank" rel="noopener">Murderpedia</a> <span class="muted small">${esc([mp.classification, mp.location].filter(Boolean).join(' · '))}</span></li>` : ''}
        ${k.links.radford
          ? `<li><a href="${esc(k.links.radford)}" target="_blank" rel="noopener">Radford University timeline</a> <span class="muted small">PDF, student-researched chronology</span></li>`
          : `<li><a href="${RADFORD_URL}" target="_blank" rel="noopener">Radford University serial killer timelines</a> <span class="muted small">no entry for this person</span></li>`}
      </ul>
      ${k.lists.length ? `<p class="muted small">Listed in: ${esc(k.lists.join('; '))}</p>` : ''}
      <p class="muted small"><a href="mailto:?subject=${encodeURIComponent('Correction: ' + k.names.primary + ' (' + k.id + ')')}">Report an error</a></p>
    </section>`;
}

// învelitoarea convexă a zonelor de activitate (monotone chain), pentru „aria” unui criminal
function hull(points: [number, number][]): [number, number][] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (const p of pts.reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

// ------------------------------------------------------------------ hartă

function themeNow(): 'light' | 'dark' {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

export interface MapApp {
  setFilters(f: Filters): number;
  setHeatmap(on: boolean): void;
  setTheme(t: 'light' | 'dark'): void;
  total(): number;
  onReady(cb: () => void): void;
}

export function initKillerMap(container: HTMLElement, panel: HTMLElement): MapApp {
  const params = new URLSearchParams(location.search);
  const map = new maplibregl.Map({
    container,
    style: STYLES[themeNow()],
    center: [10, 25],
    zoom: 1.6,
    attributionControl: {
      compact: true,
      customAttribution: 'Data: <a href="https://www.wikidata.org">Wikidata</a> (CC0), <a href="https://en.wikipedia.org">Wikipedia</a> (CC BY-SA)',
    },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

  let filtered: FeatureCollection<Point, IndexProps> = { type: 'FeatureCollection', features: [] };
  let selected: FeatureCollection = EMPTY;
  let heat = false;
  let ready = false;
  const readyCbs: (() => void)[] = [];

  function addLayers(): void {
    const dark = themeNow() === 'dark';
    const halo = dark ? '#15171c' : '#ffffff';
    map.addSource('killers', { type: 'geojson', data: filtered, cluster: true, clusterRadius: 46, clusterMaxZoom: 9 });
    map.addSource('selected', { type: 'geojson', data: selected });
    map.addSource('areas', { type: 'geojson', data: heat && areaEvents ? areaEvents : EMPTY });

    map.addLayer({
      id: 'areas-heat', type: 'heatmap', source: 'areas',
      layout: { visibility: heat ? 'visible' : 'none' },
      paint: {
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 1, 10, 6, 28],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 1, 0.6, 6, 1.4],
        'heatmap-opacity': 0.75,
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(0,0,0,0)', 0.2, 'rgba(79,124,172,0.45)', 0.5, 'rgba(208,138,46,0.7)', 1, 'rgba(192,86,59,0.9)'],
      },
    });
    map.addLayer({
      id: 'clusters', type: 'circle', source: 'killers', filter: ['has', 'point_count'],
      paint: {
        'circle-color': dark ? '#2c3e55' : '#e7edf4',
        'circle-stroke-color': dark ? '#7fa3c8' : '#4f7cac',
        'circle-stroke-width': 2,
        'circle-radius': ['step', ['get', 'point_count'], 16, 10, 20, 50, 26, 200, 33],
      },
    });
    map.addLayer({
      id: 'cluster-count', type: 'symbol', source: 'killers', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Bold'], 'text-size': 13 },
      paint: { 'text-color': dark ? '#dce7f2' : '#24405f' },
    });
    const sexColor: maplibregl.ExpressionSpecification =
      ['match', ['get', 'sex'], 'male', SEX_COLOR.male, 'female', SEX_COLOR.female, SEX_COLOR.other];
    const hollow: maplibregl.ExpressionSpecification =
      ['match', ['coalesce', ['get', 'legal'], 'undetermined'], ['suspected', 'unidentified', 'undetermined'], true, false];
    map.addLayer({
      id: 'killer-points', type: 'circle', source: 'killers', filter: ['!', ['has', 'point_count']],
      paint: {
        // precizie slabă (stat/țară) = cerc mai mare și mai transparent
        'circle-radius': ['interpolate', ['linear'], ['zoom'],
          2, ['match', ['get', 'precision'], 'country', 10, 'admin1', 9, 8],
          8, ['match', ['get', 'precision'], 'country', 14, 'admin1', 12, 11]],
        'circle-color': ['case', hollow, halo, sexColor],
        'circle-opacity': ['match', ['get', 'precision'], 'country', 0.35, 'admin1', 0.75, 0.95],
        // spree killers: contur violet gros; suspecți/neverificați: inel gol în culoarea sexului
        'circle-stroke-color': ['case', ['in', 'mass', ['coalesce', ['get', 'type'], '']], MASS_COLOR,
          ['in', 'spree', ['coalesce', ['get', 'type'], '']], SPREE_COLOR, hollow, sexColor, halo],
        'circle-stroke-width': ['case', ['in', 'mass', ['coalesce', ['get', 'type'], '']], 3.5,
          ['in', 'spree', ['coalesce', ['get', 'type'], '']], 3.5, hollow, 3, 1.5],
      },
    });
    map.addLayer({
      id: 'killer-labels', type: 'symbol', source: 'killers', filter: ['!', ['has', 'point_count']], minzoom: 6,
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 12,
        'text-offset': [0, 1.3], 'text-anchor': 'top', 'text-optional': true },
      paint: { 'text-color': dark ? '#d7dbe2' : '#2a2d33', 'text-halo-color': halo, 'text-halo-width': 1.4 },
    });
    map.addLayer({
      id: 'selected-area', type: 'fill', source: 'selected', filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': KIND_COLOR.active_area, 'fill-opacity': dark ? 0.16 : 0.12 },
    });
    map.addLayer({
      id: 'selected-area-outline', type: 'line', source: 'selected', filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'line-color': KIND_COLOR.active_area, 'line-width': 1.2, 'line-opacity': 0.55 },
    });
    map.addLayer({
      id: 'selected-line', type: 'line', source: 'selected', filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': KIND_COLOR.active_area, 'line-width': 1.5, 'line-dasharray': [2, 2], 'line-opacity': 0.7 },
    });
    map.addLayer({
      id: 'selected-points', type: 'circle', source: 'selected', filter: ['==', ['geometry-type'], 'Point'],
      paint: {
        'circle-radius': 9,
        'circle-color': ['match', ['get', 'kind'], 'birth', KIND_COLOR.birth, 'death', KIND_COLOR.death, KIND_COLOR.active_area],
        'circle-stroke-color': halo, 'circle-stroke-width': 2.5,
      },
    });
    map.addLayer({
      id: 'selected-labels', type: 'symbol', source: 'selected', filter: ['==', ['geometry-type'], 'Point'],
      layout: {
        'text-field': ['concat', ['match', ['get', 'kind'], 'birth', 'Born · ', 'death', 'Died · ', ''], ['get', 'place_name']],
        'text-font': ['Noto Sans Regular'], 'text-size': 12.5, 'text-offset': [0, 1.35], 'text-anchor': 'top',
      },
      paint: { 'text-color': dark ? '#f0f2f5' : '#1d1f24', 'text-halo-color': halo, 'text-halo-width': 1.8 },
    });
  }

  map.on('style.load', () => {
    addLayers();
  });

  map.on('load', async () => {
    const data = (await fetch(`${DATA}/killers-index.geojson`).then((r) => r.json())) as FeatureCollection<Point, IndexProps>;
    index = data.features;
    ready = true;
    readyCbs.splice(0).forEach((cb) => cb());
    const initial = params.get('k');
    if (initial) void select(initial);
  });

  map.on('click', 'clusters', async (e) => {
    const f = e.features?.[0];
    if (!f) return;
    const src = map.getSource('killers') as maplibregl.GeoJSONSource;
    const zoom = await src.getClusterExpansionZoom(f.properties.cluster_id as number);
    map.easeTo({ center: (f.geometry as Point).coordinates as [number, number], zoom: zoom + 0.2 });
  });
  map.on('click', 'killer-points', (e) => {
    const id = e.features?.[0]?.properties?.id as string | undefined;
    if (id) void select(id);
  });
  for (const layer of ['clusters', 'killer-points']) {
    map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''));
  }
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'hover-pop' });
  map.on('mousemove', 'killer-points', (e) => {
    const p = e.features?.[0]?.properties;
    if (!p) return;
    const years = p.from ? ` · ${p.from}${p.to && p.to !== p.from ? '–' + p.to : ''}` : '';
    popup.setLngLat(e.lngLat)
      .setHTML(`<strong>${esc(p.name)}</strong><span>${esc(p.place)}${p.precision === 'country' ? ' · country only, exact area unknown' : ''}${esc(years)}</span>`)
      .addTo(map);
  });
  map.on('mouseleave', 'killer-points', () => popup.remove());

  const body = panel.querySelector('.panel-body') as HTMLElement;
  async function select(id: string): Promise<void> {
    panel.hidden = false;
    document.body.classList.add('has-panel');
    body.innerHTML = '<p class="muted">Loading…</p>';
    await loadDetails();
    const k = killersById!.get(id);
    if (!k) {
      body.innerHTML = '<p>Not found.</p>';
      return;
    }
    const evs = eventsByKiller!.get(id) ?? [];
    body.innerHTML = renderPanel(k, evs);
    panel.scrollTop = 0;
    // fără linie între zone: ordinea lor nu e cronologică (linia vine cu evenimentele datate, faza 3).
    // Cu ≥ 3 zone, aria lor (învelitoarea convexă) arată întinderea geografică a activității.
    const feats: Feature[] = [...evs];
    const areaPts = evs.filter((e) => e.properties.kind === 'active_area')
      .map((e) => e.geometry.coordinates as [number, number]);
    const ring = hull(areaPts);
    if (ring.length >= 3) {
      feats.unshift({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
    }
    selected = { type: 'FeatureCollection', features: feats };
    (map.getSource('selected') as maplibregl.GeoJSONSource).setData(selected);
    if (evs.length) {
      const b = new maplibregl.LngLatBounds();
      evs.forEach((f) => b.extend(f.geometry.coordinates as [number, number]));
      const mobile = innerWidth < 760;
      map.fitBounds(b, {
        padding: mobile ? { top: 70, bottom: innerHeight * 0.55, left: 40, right: 40 }
          : { top: 90, bottom: 60, left: 380, right: Math.min(480, innerWidth * 0.4) },
        maxZoom: 7,
      });
    }
    const url = new URL(location.href);
    url.searchParams.set('k', id);
    history.replaceState(null, '', url);
  }

  panel.querySelector('.close')?.addEventListener('click', () => {
    panel.hidden = true;
    document.body.classList.remove('has-panel');
    selected = EMPTY;
    (map.getSource('selected') as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY);
    const url = new URL(location.href);
    url.searchParams.delete('k');
    history.replaceState(null, '', url);
  });

  let fitOnce = Boolean(params.get('c')) && !params.get('k');
  return {
    total: () => index.length,
    onReady(cb) {
      if (ready) cb();
      else readyCbs.push(cb);
    },
    setFilters(f) {
      filtered = { type: 'FeatureCollection', features: index.filter((x) => matches(x.properties, f)) };
      (map.getSource('killers') as maplibregl.GeoJSONSource | undefined)?.setData(filtered);
      if (fitOnce && filtered.features.length) {
        fitOnce = false;
        const b = new maplibregl.LngLatBounds();
        filtered.features.forEach((x) => b.extend(x.geometry.coordinates as [number, number]));
        map.fitBounds(b, { padding: 70, maxZoom: 7, duration: 0 });
      }
      return filtered.features.length;
    },
    async setHeatmap(on) {
      heat = on;
      if (on) await loadDetails();
      (map.getSource('areas') as maplibregl.GeoJSONSource | undefined)?.setData(on && areaEvents ? areaEvents : EMPTY);
      if (map.getLayer('areas-heat')) map.setLayoutProperty('areas-heat', 'visibility', on ? 'visible' : 'none');
    },
    setTheme(t) {
      map.setStyle(STYLES[t], { diff: false });
    },
  };
}
