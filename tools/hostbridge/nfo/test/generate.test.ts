import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseFlp, writeFlp, firstDiff } from '../../../flp/src/flp.ts';
import { parseWrapperData } from '../../../flp/src/summary.ts';
import { generateDb, magicOf, DEFAULT_DB_PATH, type PluginSpec } from '../src/generate.ts';
import { entryFromBytes } from '../src/entry.ts';
import { ValueFile, decodeText } from '../src/valuefile.ts';
import { guidToString, tuidFromHex, slotOf } from '../src/format.ts';

const specs: PluginSpec[] = JSON.parse(readFileSync(new URL('../specs/wasm_plugins.json', import.meta.url), 'utf8')).plugins;

test('magicOf: 4-char string = big-endian u32 (uniqueID), signed int32', () => {
  assert.equal(magicOf('XfTT'), 0x58665454);
  assert.equal(magicOf('\u00ffabc') < 0, true);
  assert.throws(() => magicOf('abc'));
});

test('generated DB: layout, every entry accepted by the FL-reader model, preset file present and consistent', () => {
  const g = generateDb(specs);
  assert.deepEqual([...g.files.keys()].sort(), [
    'Installed/Effects/VST/Fresh Air.fst', 'Installed/Effects/VST/Fresh Air.nfo',
    'Installed/Effects/VST/OTT.fst', 'Installed/Effects/VST/OTT.nfo',
    'Installed/Effects/VST3/Serum 2 FX.fst', 'Installed/Effects/VST3/Serum 2 FX.nfo',
    'Installed/Generators/VST3/Serum 2.fst', 'Installed/Generators/VST3/Serum 2.nfo',
    'Installed/VerifiedIDs.nfo',
  ]);
  for (const e of g.entries) {
    const r = entryFromBytes(g.files.get(e.nfo)!, { dbPath: DEFAULT_DB_PATH });
    assert.equal(r.dropped, undefined, e.nfo);
    assert.deepEqual(r.rejectedFiles, []);
    const f = r.entry!.files[0];
    assert.ok(slotOf(f.plugclass, f.bits) >= 0);
    assert.equal(f.filename, e.spec.path);
    assert.equal(r.entry!.name, e.spec.name);
    // ps_presetfilename resolves (after %FLPluginDBPath% expansion) to a generated fst
    const rel = r.entry!.presetFilename.slice(DEFAULT_DB_PATH.length + 1).replace(/\\/g, '/');
    assert.ok(g.files.has(rel), rel);
    // fst ↔ nfo consistency through the independent tools/flp parser
    const fl = parseFlp(g.files.get(rel)!);
    assert.equal(firstDiff(g.files.get(rel)!, writeFlp(fl)), -1);
    const data = fl.events.find((x) => x.id === 213)!.data;
    const w = parseWrapperData(data)!;
    assert.equal(w.path, e.spec.path);
    assert.equal(w.vendor, e.spec.vendor);
    const name203 = new TextDecoder('utf-16le').decode(fl.events.find((x) => x.id === 203)!.data).replace(/\0+$/, '');
    assert.equal(name203, e.spec.name);
    if (e.spec.format === 'vst3') {
      assert.equal(guidToString(f.guid), guidToString(tuidFromHex(e.spec.guid!)));
      assert.equal(w.kind, 8);
    } else {
      assert.equal(f.magic, magicOf(e.spec.magic));
    }
  }
});

test('Serum 2 generator vs FX land in different top-level folders and classes (8 vs 7)', () => {
  const g = generateDb(specs);
  const cls = (rel: string): number => entryFromBytes(g.files.get(rel)!).entry!.files[0].plugclass;
  assert.equal(cls('Installed/Generators/VST3/Serum 2.nfo'), 8);
  assert.equal(cls('Installed/Effects/VST3/Serum 2 FX.nfo'), 7);
  assert.equal(cls('Installed/Effects/VST/OTT.nfo'), 0);
});

test('VerifiedIDs.nfo: key = <fmt>:<GUID>:<bits>, value = nfo path relative to Installed\\ with .NFO', () => {
  const g = generateDb(specs);
  const vf = ValueFile.parse(decodeText(g.files.get('Installed/VerifiedIDs.nfo')!));
  assert.equal(vf.get('VST3:{58455356-7366-7350-6572-756D20320000}:64'), 'Generators\\VST3\\Serum 2.NFO');
  assert.equal(vf.lines.length, 4);
  assert.equal(generateDb(specs, { verifiedIds: false }).files.has('Installed/VerifiedIDs.nfo'), false);
});

test('same-name 32+64 specs merge into one two-file entry; sanitised file names', () => {
  const base: PluginSpec = { name: 'A/B: x', vendor: 'V', format: 'vst2', kind: 'effect', magic: 'ABCD', path: 'C:\\a64.dll' };
  const g = generateDb([base, { ...base, bits: 32, path: 'C:\\a32.dll' }]);
  assert.ok(g.files.has('Installed/Effects/VST/A-B- x.nfo'));
  const e = entryFromBytes(g.files.get('Installed/Effects/VST/A-B- x.nfo')!).entry!;
  assert.deepEqual(e.files.map((f) => [f.bits, f.filename]), [[3, 'C:\\a64.dll'], [2, 'C:\\a32.dll']]);
  const w = parseWrapperData(parseFlp(g.files.get('Installed/Effects/VST/A-B- x.fst')!).events.find((x) => x.id === 213)!.data)!;
  assert.equal(w.path, undefined); // multi-file entry: FL drops the path record
});

test('output is deterministic', () => {
  const a = generateDb(specs), b = generateDb(specs);
  for (const [k, v] of a.files) assert.deepEqual(v, b.files.get(k));
});
