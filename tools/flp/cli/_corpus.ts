// Node-only corpus helpers (file walker, default roots).
import { readdirSync, readFileSync, lstatSync } from 'node:fs';
import { join, relative } from 'node:path';
import { isFlpMagic } from '../src/flp.ts';

export const DEFAULT_FL_ROOT =
  '/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL';

export function flRoot(): string {
  return process.env.FL_ROOT ?? DEFAULT_FL_ROOT;
}

export interface CorpusFile {
  /** path relative to FL root (stable key) */
  rel: string;
  abs: string;
  ext: string;
  /** coarse class: demo | template | render-test | system-flp | fst | fsc | other */
  group: string;
}

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const st = lstatSync(p);
    if (st.isSymbolicLink()) continue;
    if (st.isDirectory()) yield* walk(p);
    else if (st.isFile()) yield p;
  }
}

export function classify(rel: string, ext: string): string {
  if (ext === 'flp') {
    if (rel.startsWith('Data/Demo projects/')) return 'demo';
    if (rel.startsWith('Data/Templates/')) return 'template';
    if (rel.startsWith('Data/System/Render tests/')) return 'render-test';
    return 'system-flp';
  }
  if (ext === 'fst') return 'fst';
  if (ext === 'fsc') return 'fsc';
  return 'other';
}

/** all files whose first 4 bytes are "FLhd" (any extension), sorted by rel path */
export function listFlhdFiles(root = flRoot()): CorpusFile[] {
  const out: CorpusFile[] = [];
  for (const abs of walk(root)) {
    const dot = abs.lastIndexOf('.');
    const ext = dot >= 0 ? abs.slice(dot + 1).toLowerCase() : '';
    const rel = relative(root, abs);
    // cheap pre-filter on extension, then verify magic
    if (!['flp', 'fst', 'fsc'].includes(ext)) {
      const head = readFileSync(abs).subarray(0, 4);
      if (!isFlpMagic(head)) continue;
    }
    out.push({ rel, abs, ext, group: classify(rel, ext) });
  }
  return out;
}
