// Copiază datele exportate de pipeline (../data) în public/data, înainte de dev/build.
import { cpSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(site, '..', 'data');
const dst = join(site, 'public', 'data');
mkdirSync(dst, { recursive: true });
const files = readdirSync(src).filter((f) => /\.(json|geojson)$/.test(f));
for (const f of files) cpSync(join(src, f), join(dst, f));
console.log(`copy-data: ${files.length} fișiere din data/ în public/data/`);
