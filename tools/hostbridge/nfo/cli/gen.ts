// CLI: node cli/gen.ts <specs.json> <outDir> [--kilohearts <product_index.json>] [--db-path <win path>] [--no-verified-ids]
// Writes the synthetic `Presets/Plugin database` tree (Installed/**) under <outDir>.
import { readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { generateDb, type PluginSpec } from '../src/generate.ts';

const args = process.argv.slice(2);
const flag = (n: string): string | undefined => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const [specPath, outDir] = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--') && args[i - 1] !== '--no-verified-ids'));
if (!specPath || !outDir) {
  console.error('usage: node cli/gen.ts <specs.json> <outDir> [--kilohearts product_index.json] [--db-path <win path>] [--no-verified-ids]');
  process.exit(2);
}
const specs: PluginSpec[] = JSON.parse(readFileSync(specPath, 'utf8')).plugins;
const kh = flag('--kilohearts');
if (kh && existsSync(kh)) {
  const idx = JSON.parse(readFileSync(kh, 'utf8')).plugins as Array<{ id: string; displayName: string; fileName: string; formats: string[] }>;
  for (const p of idx) {
    if (!p.formats.includes('vst2') || p.id.length !== 4) continue;
    // Real machine (CAB-218, analysis/kh_magic_check.mjs): product id == measured VST2 uniqueID (45/45), category is
    // "Effect" on all 44 KH VST2 fx; Phase Plant is the only KH generator (Generators\VST, category "Synth").
    const gen = p.fileName === 'Phase Plant';
    specs.push({ name: p.fileName, vendor: 'Kilohearts', format: 'vst2', kind: gen ? 'generator' : 'effect', magic: p.id, path: `C:\\Program Files\\Common Files\\VST2\\Kilohearts\\${p.fileName}.dll`, category: gen ? 'Synth' : 'Effect' });
  }
}
const res = generateDb(specs, { dbPath: flag('--db-path'), verifiedIds: !args.includes('--no-verified-ids') });
for (const [rel, bytes] of res.files) {
  const p = join(outDir, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, bytes);
}
console.log(`generated ${res.entries.length} entries, ${res.files.size} files -> ${outDir}`);
