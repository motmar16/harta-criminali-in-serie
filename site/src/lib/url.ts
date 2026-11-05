// Căile site-ului țin cont de `base` (pe GitHub Pages site-ul stă în /harta-criminali-in-serie/).
const BASE = import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL.slice(0, -1) : import.meta.env.BASE_URL;

export const url = (path: string): string => `${BASE}${path.startsWith('/') ? path : '/' + path}`;
