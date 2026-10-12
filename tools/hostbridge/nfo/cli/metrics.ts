// Prints/stores the measured numbers quoted in REPORT.md. node cli/metrics.ts [out.json]
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { parseFlp } from '../../../flp/src/flp.ts';
import { ValueFile, decodeText } from '../src/valuefile.ts';
import { readNativePluginNfo, entryFromBytes } from '../src/entry.ts';
import { assembleFst } from '../src/fst.ts';
import { generateDb, DEFAULT_DB_PATH, type PluginSpec } from '../src/generate.ts';
import { FL_ROOT, HAVE_FL, filesWithExt, read } from '../test/_fl.ts';
import { REPO_ROOT } from '../../../shared/paths.mjs';

const out: Record<string, unknown> = { flRoot: FL_ROOT, haveFl: HAVE_FL };
if (HAVE_FL) {
  const nfos = filesWithExt(FL_ROOT, '.nfo');
  let rt = 0, bytes = 0, nonAscii = 0;
  const keys = new Map<string, number>();
  for (const f of nfos) {
    const raw = read(f);
    bytes += raw.length;
    if (raw.some((x) => x > 0x7f)) { nonAscii++; continue; }
    const t = decodeText(raw);
    const vf = ValueFile.parse(t);
    if (vf.toString() === t) rt++;
    for (const k of vf.keys()) keys.set(k.toLowerCase(), (keys.get(k.toLowerCase()) ?? 0) + 1);
  }
  const plugNfo = filesWithExt(`${FL_ROOT}/Plugins/Fruity`, 'plugin.nfo');
  const vendors = new Map<string, number>();
  let dummy = 0;
  for (const f of plugNfo) {
    const r = readNativePluginNfo(ValueFile.parse(decodeText(read(f))));
    vendors.set(r.vendor, (vendors.get(r.vendor) ?? 0) + 1);
    if (r.dummy64bit) dummy++;
  }
  const dbFst = filesWithExt(`${FL_ROOT}/Data/System/Plugin databases`, '.fst');
  const dbNfo = filesWithExt(`${FL_ROOT}/Data/System/Plugin databases`, '.nfo');
  let repro = 0, v1155 = 0, psKeyFiles = 0;
  for (const p of dbFst) {
    const raw = read(p);
    const f = parseFlp(raw);
    if (new TextDecoder().decode(f.events[0].data) !== '11.5.5\0') continue;
    v1155++;
    const again = assembleFst(f.events.map((e) => ({ id: e.id, data: e.data })), { format: f.header.format, nChannels: f.header.nChannels, ppq: f.header.ppq });
    if (again.length === raw.length && again.every((x, i) => x === raw[i])) repro++;
  }
  for (const f of nfos) if (/\bps_/i.test(decodeText(read(f)))) psKeyFiles++;
  const wrapperFst = dbFst.filter((p) => { const f = parseFlp(read(p)); return f.events.some((e) => e.id === 201 && new TextDecoder('utf-16le').decode(e.data).startsWith('Fruity Wrapper')); }).length;
  Object.assign(out, {
    nfoFilesTotal: nfos.length, nfoBytes: bytes, nfoNonAscii: nonAscii, nfoRoundTripExact: rt, nfoKeyHistogram: Object.fromEntries([...keys].sort((a, b) => b[1] - a[1])),
    nativePluginNfo: plugNfo.length, nativeVendors: Object.fromEntries(vendors), nativeDummy64bit: dummy,
    dbDirNfo: dbNfo.length, dbDirFst: dbFst.length, nfoFilesWithPsKeys: psKeyFiles, dbFstWithWrapperInternalName: wrapperFst,
    fst1155Files: v1155, fst1155ReproducedExact: repro,
  });
}
const specs: PluginSpec[] = JSON.parse(readFileSync(new URL('../specs/wasm_plugins.json', import.meta.url), 'utf8')).plugins;
const khp = `${REPO_ROOT}/tools/targets/kilohearts/work/macpkg/product_index.json`;
if (existsSync(khp)) {
  for (const p of JSON.parse(readFileSync(khp, 'utf8')).plugins as Array<{ id: string; fileName: string; formats: string[] }>) {
    // "Effect" on all 44 KH VST2 fx; Phase Plant is the only KH generator (Generators\VST, category "Synth") — same rule as cli/gen.ts / h4/specs.ts.
    const gen = p.fileName === 'Phase Plant';
    if (p.formats.includes('vst2') && p.id.length === 4) specs.push({ name: p.fileName, vendor: 'Kilohearts', format: 'vst2', kind: gen ? 'generator' : 'effect', magic: p.id, path: `C:\\Program Files\\Common Files\\VST2\\Kilohearts\\${p.fileName}.dll`, category: gen ? 'Synth' : 'Effect' });
  }
}
const g = generateDb(specs);
let accepted = 0, bytes = 0;
for (const e of g.entries) {
  const r = entryFromBytes(g.files.get(e.nfo)!, { dbPath: DEFAULT_DB_PATH });
  if (r.entry && r.rejectedFiles.length === 0) accepted++;
}
for (const v of g.files.values()) bytes += v.length;
Object.assign(out, { generatedEntries: g.entries.length, generatedFiles: g.files.size, generatedBytes: bytes, readerAccepted: accepted });
console.log(JSON.stringify(out, null, 1));
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(out, null, 1));
