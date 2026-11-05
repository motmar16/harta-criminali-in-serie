// Citire la build a datelor generate de pipeline (site/public/data/). Vite nu permite import din public/.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export function readData<T>(name: string): T {
  return JSON.parse(readFileSync(resolve(process.cwd(), 'public', 'data', name), 'utf-8')) as T;
}

export interface Coverage { killers_total: number; generated_at: string; [k: string]: unknown }
export interface CountryRow { code: string; name: string; killers: number }
export interface KillerRow {
  id: string;
  names: { primary: string };
  description: string | null;
  countries: string[];
  active: { start: string; end: string } | null;
  victims: { proven: number | null; possible: number | null } | null;
  legal_status: string | null;
  links: { wikipedia: string | null };
}
