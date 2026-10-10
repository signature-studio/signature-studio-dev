import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Vreg } from '../js/vreg.mjs';
import { MemoryStore } from '../js/store.mjs';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const seed = JSON.parse(readFileSync(path.join(ROOT, 'data/seed.json'), 'utf8'));
export const keysJson = JSON.parse(readFileSync(path.join(ROOT, 'data/keys.json'), 'utf8'));
const WASM = path.join(ROOT, 'build/vreg_wasm.mjs');
if (!existsSync(WASM)) throw new Error('build/vreg_wasm.mjs が無い: bash build.sh module を先に実行');
export const createModule = (await import(WASM)).default;

/** 毎回新しい wasm instance (= プロセス再起動相当)。store を共有すれば「リロード」 */
export function boot(opts = {}) {
  return Vreg.create({ createModule, seed, store: opts.store ?? new MemoryStore(), flushDelayMs: 0, ...opts });
}
export const GEN = 'Software\\Image-Line\\FL Studio 26\\General';
export const PATHS = 'Software\\Image-Line\\Shared\\Paths';
export const CV = 'SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion';
