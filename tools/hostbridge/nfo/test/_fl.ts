import { readdirSync, lstatSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { FL_MAC_DIR } from '../../../shared/paths.mjs';

export const FL_ROOT =
  process.env.FL_ROOT ??
  `${FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL`;

export const HAVE_FL = existsSync(FL_ROOT);

export function* walk(dir: string): Generator<string> {
  for (const n of readdirSync(dir).sort()) {
    const p = join(dir, n);
    const st = lstatSync(p);
    if (st.isSymbolicLink()) continue;
    if (st.isDirectory()) yield* walk(p);
    else if (st.isFile()) yield p;
  }
}

export function filesWithExt(root: string, ext: string): string[] {
  return [...walk(root)].filter((p) => p.toLowerCase().endsWith(ext));
}

export const read = (p: string): Uint8Array => new Uint8Array(readFileSync(p));
