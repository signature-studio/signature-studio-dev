// specs.ts — CAB-216: e2e で使う plugin spec 集合の構築 (node / browser 共通)。
// cli/gen.ts の Kilohearts 展開規則と同一 (product_index.json の 4 文字 id = VST2 uniqueID, CAB-218 実測 45/45)。
// browser-safe (node: import 無し)。JSON 文字列を渡す。
import type { PluginSpec } from '../src/generate.ts';

export interface KhIndex { plugins: Array<{ id: string; displayName: string; fileName: string; formats: string[] }> }

export const KH_VENDOR = 'Kilohearts';

/** wasm_plugins.json の plugins 配列 + Kilohearts index 展開 → 完全な spec 配列。 */
export function buildSpecs(specsJson: string, khIndexJson: string | null): PluginSpec[] {
  const specs: PluginSpec[] = JSON.parse(specsJson).plugins as PluginSpec[];
  if (khIndexJson) {
    for (const p of JSON.parse(khIndexJson).plugins as KhIndex['plugins']) {
      if (!p.formats.includes('vst2') || p.id.length !== 4) continue;
      // Real machine (CAB-218, analysis/kh_magic_check.mjs): product id == measured VST2 uniqueID (45/45), category is
      // "Effect" on all 44 KH VST2 fx; Phase Plant is the only KH generator (Generators\VST, category "Synth").
      const gen = p.fileName === 'Phase Plant';
      specs.push({
        name: p.fileName, vendor: KH_VENDOR, format: 'vst2', kind: gen ? 'generator' : 'effect', magic: p.id,
        path: `C:\\Program Files\\Common Files\\VST2\\Kilohearts\\${p.fileName}.dll`, category: gen ? 'Synth' : 'Effect',
      });
    }
  }
  return specs;
}

/** 集計 (数え方の定義は REPORT §13.2 / analysis/h4_recount.mjs と対になる)。 */
export interface SpecCounts {
  total: number;
  byFormat: Record<string, number>;
  byKind: Record<string, number>;
  byVendor: Record<string, number>;
  /** Kilohearts index 由来 (product_index の 4 文字 id + vst2) の件数 */
  fromKiloheartsIndex: number;
  /** specs JSON 由来の件数 */
  fromSpecsJson: number;
}

export function countSpecs(specs: PluginSpec[], khIndexJson: string | null): SpecCounts {
  const c: SpecCounts = { total: specs.length, byFormat: {}, byKind: {}, byVendor: {}, fromKiloheartsIndex: 0, fromSpecsJson: 0 };
  for (const s of specs) {
    c.byFormat[s.format] = (c.byFormat[s.format] ?? 0) + 1;
    c.byKind[s.kind] = (c.byKind[s.kind] ?? 0) + 1;
    c.byVendor[s.vendor] = (c.byVendor[s.vendor] ?? 0) + 1;
  }
  if (khIndexJson) {
    const n = JSON.parse(khIndexJson).plugins.filter((p: KhIndex['plugins'][number]) => p.formats.includes('vst2') && p.id.length === 4).length;
    c.fromKiloheartsIndex = n;
    c.fromSpecsJson = specs.length - n;
  } else c.fromSpecsJson = specs.length;
  return c;
}
