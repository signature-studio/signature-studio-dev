// Real-machine fixture validation (CAB-219): the user's actual `Installed\.Plugins.ini` / `Installed\VerifiedIDs.nfo`
// (FL Studio 26.1.7 win64, %USERPROFILE%\Documents\Image-Line\FL Studio\Presets\Plugin database\).
// Proves the writer/reader models against 406 real entries and 236 real ID keys. See REPORT.md §11.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ValueFile, decodeText } from '../src/valuefile.ts';
import { IniFile } from '../src/ini.ts';
import { readEntry, writeEntry, bitsToTDateTime, tDateTimeToIso, tDateTimeToBits } from '../src/entry.ts';
import { scanFlagsFromDisk, vst2PseudoGuid, guidToString, delimitedParse } from '../src/format.ts';
import { generateDb, type PluginSpec } from '../src/generate.ts';

const dir = new URL('../evidence/real_machine/', import.meta.url);
const iniRaw = new Uint8Array(readFileSync(new URL('.Plugins.ini', dir)));
const verRaw = new Uint8Array(readFileSync(new URL('VerifiedIDs.nfo', dir)));
const iniOf = (sec: { lines: string[] }): ValueFile => new ValueFile([...sec.lines]);

test('real .Plugins.ini: UTF-8 with BOM, 406 sections, parse→serialize byte-exact round-trip', () => {
  assert.deepEqual([...iniRaw.slice(0, 3)], [0xef, 0xbb, 0xbf]);
  const ini = IniFile.fromBytes(iniRaw);
  assert.equal(ini.sections.length, 406);
  assert.equal(new Set(ini.sections.map((s) => s.name.toUpperCase())).size, 406); // no duplicates
  assert.deepEqual(ini.toBytes(), iniRaw);
});

test('real .Plugins.ini: every section accepted by the FL reader model; writer reproduces every section', () => {
  const ini = IniFile.fromBytes(iniRaw);
  let decorated = 0;
  for (const sec of ini.sections) {
    const vf = iniOf(sec);
    const r = readEntry(vf);
    assert.equal(r.dropped, undefined, sec.name);
    assert.deepEqual(r.rejectedFiles, [], sec.name);
    const e = r.entry!;
    let opts = {};
    if (vf.get('iconindex') !== undefined) {
      // FL wrote these with the runtime "new" flag 8 (masked out of the persisted scanflags); emulate it
      decorated++;
      e.files[0] = { ...e.files[0], scanflags: scanFlagsFromDisk(1) | 8 };
      opts = { newDecoration: { tip: vf.getString('tip') } };
    }
    assert.deepEqual(writeEntry(e, opts).lines, sec.lines, sec.name);
  }
  assert.equal(decorated, 6); // iconindex/color/tip decorations observed on 6 real sections
});

test('real .Plugins.ini: stats (407 files, 139 natives, arch=Intel 407/407, scanflags 1/2/0x22, one 2-file entry)', () => {
  const ini = IniFile.fromBytes(iniRaw);
  let files = 0;
  const arch = new Map<string, number>();
  const sf = new Map<string, number>();
  let natives = 0;
  let multi = 0;
  for (const sec of ini.sections) {
    const vf = iniOf(sec);
    const n = Number(vf.getString('ps_files'));
    files += n;
    if (n >= 2) multi++;
    if (/\\Fruity\\/.test(sec.name)) natives++;
    for (let i = 0; i < n; i++) {
      const a = vf.getString(`ps_file_arch_${i}`);
      arch.set(a, (arch.get(a) ?? 0) + 1);
      const s = vf.getString(`ps_file_scanflags_${i}`);
      sf.set(s, (sf.get(s) ?? 0) + 1);
    }
  }
  assert.equal(files, 407);
  assert.equal(natives, 139);
  assert.equal(multi, 1);
  assert.deepEqual(Object.fromEntries(arch), { Intel: 407 });
  assert.deepEqual(Object.fromEntries(sf), { '1': 363, '2': 26, '34': 18 }); // 363 = 362 entries + Vital file 1
});

test('real .Plugins.ini: ps_file_date = TDateTime double bits (spot + all-407 sane range)', () => {
  // 4676583981019826458 = double bits of TDateTime 46210.8250694… = 2026-07-07 19:48:06 (a plausible install time)
  const td = bitsToTDateTime(4676583981019826458n);
  assert.equal(tDateTimeToIso(td), '2026-07-07T19:48:06.000Z');
  assert.equal(tDateTimeToBits(td), 4676583981019826458n);
  const ini = IniFile.fromBytes(iniRaw);
  let n = 0;
  let min = Infinity;
  let max = -Infinity;
  for (const sec of ini.sections) {
    const vf = iniOf(sec);
    for (const k of vf.keys()) {
      if (!k.toLowerCase().startsWith('ps_file_date_')) continue;
      const d = bitsToTDateTime(BigInt(vf.getString(k)));
      assert.ok(d > 30000 && d < 80000, `${sec.name} ${k} = ${d}`); // 1982..2119 sanity window
      min = Math.min(min, d);
      max = Math.max(max, d);
      n++;
    }
  }
  assert.equal(n, 407);
  assert.ok(tDateTimeToIso(min).startsWith('2015-10-22'));
  assert.ok(tDateTimeToIso(max).startsWith('2026-09-29'));
});

test('real VerifiedIDs.nfo: value file round-trip, 236 unique keys, id shape per family', () => {
  const text = decodeText(verRaw);
  const vf = ValueFile.parse(text);
  assert.equal(vf.lines.length, 236);
  assert.equal(vf.toString(), text); // lossless
  assert.equal(new Set(vf.lines.map((l) => l.slice(0, l.indexOf('=')))).size, 236);
  const counts: Record<string, number> = {};
  for (const line of vf.lines) {
    const m = /^(VST|VST3|AU|CLAP|FL|DX):(32|64):(.+)=(Effects|Generators)\\.+\.NFO$/.exec(line);
    assert.ok(m, line);
    counts[m[1]] = (counts[m[1]] ?? 0) + 1;
    if (m[1] === 'VST') assert.match(m[3], /^\d+$/); // ps_file_magic decimal (signed int32; no sample ≥ 2^31)
    else if (m[1] === 'VST3') assert.match(m[3], /^\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}$/);
  }
  assert.deepEqual(counts, { VST: 64, VST3: 171, CLAP: 1 });
});

test('real VerifiedIDs ↔ .Plugins.ini: every key matches ps_file_magic / guid / idstring / compat (236/236)', () => {
  const vf = ValueFile.parse(decodeText(verRaw));
  const ini = IniFile.fromBytes(iniRaw);
  for (const line of vf.lines) {
    const p = line.indexOf('=');
    const key = line.slice(0, p);
    const val = line.slice(p + 1);
    const sec = ini.get(val.replace(/\.NFO$/i, ''));
    assert.ok(sec, val);
    const svf = iniOf(sec);
    const m = /^(VST|VST3|CLAP):(32|64):(.+)$/.exec(key)!;
    if (m[1] === 'VST') {
      const magics = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_magic_')).map((k) => svf.getString(k));
      assert.ok(magics.includes(m[3]), key);
    } else if (m[1] === 'VST3') {
      // id = ps_file_guid of some file, or one of the ps_compatibility GUID aliases (real example: Splice INSTRUMENT
      // has 5 keys = its guid + 4 compat GUIDs — that is what ps_compatibility is for)
      const guids = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_guid_')).map((k) => svf.getString(k).toUpperCase());
      for (const k of svf.keys().filter((k) => k.toLowerCase().startsWith('ps_compatibility_'))) {
        guids.push(...delimitedParse(svf.getString(k)).map((x) => x.toUpperCase()));
      }
      assert.ok(guids.includes(m[3].toUpperCase()), key);
    } else {
      const ids = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_idstring_')).map((k) => svf.getString(k));
      assert.ok(ids.includes(m[3]), key);
    }
  }
});

test('real VerifiedIDs covers exactly the non-native scanflags=1 entries (236 keys → 223 nfos)', () => {
  const vf = ValueFile.parse(decodeText(verRaw));
  const ini = IniFile.fromBytes(iniRaw);
  const referenced = new Set(vf.lines.map((l) => l.slice(l.indexOf('=') + 1).replace(/\.NFO$/i, '')));
  assert.equal(referenced.size, 223);
  const expected = new Set(
    ini.sections
      .filter((s) => !/\\Fruity\\/.test(s.name) && iniOf(s).getString('ps_file_scanflags_0') === '1')
      .map((s) => s.name),
  );
  assert.deepEqual(referenced, expected);
});

test('real VST2 ps_file_guid = "VST"+magic4+lower(name) — vst2PseudoGuid reproduces all 64', () => {
  const ini = IniFile.fromBytes(iniRaw);
  let n = 0;
  for (const sec of ini.sections) {
    const vf = iniOf(sec);
    for (let i = 0; i < Number(vf.getString('ps_files') || 0); i++) {
      const magic = vf.get(`ps_file_magic_${i}`);
      if (magic === undefined) continue; // VST3 files carry no magic
      const g = vf.get(`ps_file_guid_${i}`);
      if (g === undefined) continue; // scanflags=2 stub entries carry magic but no guid
      const name = vf.getString(`ps_file_name_${i}`) || vf.getString('ps_name');
      assert.equal(guidToString(vst2PseudoGuid(name, Number(magic) | 0)), g, `${sec.name} #${i}`);
      n++;
    }
  }
  assert.equal(n, 64);
});

test('generated Serum 2 entries match the real machine sections/keys (minus unobservable date/size)', () => {
  const specs: PluginSpec[] = JSON.parse(readFileSync(new URL('../specs/wasm_plugins.json', import.meta.url), 'utf8')).plugins;
  const g = generateDb(specs);
  const ini = IniFile.fromBytes(iniRaw);
  // ps_file_date/size: real scanner values unknown for our synthetic DB. ps_file_filename now matches too —
  // CAB-218 determined the rule (ps_file_filename = the loadable module FILE path, consumed verbatim down to
  // LoadLibraryW), so the spec carries the real machine's inner-binary form (…\Contents\x86_64-win\Serum2.vst3).
  const drop = new Set(['ps_file_date_0', 'ps_file_size_0']);
  const strip = (lines: string[]): string[] => lines.filter((l) => !drop.has(l.slice(0, l.indexOf('=')).toLowerCase()));
  for (const name of ['Generators\\VST3\\Serum 2', 'Effects\\VST3\\Serum 2 FX']) {
    const gen = ValueFile.parse(decodeText(g.files.get(`Installed/${name.replace(/\\/g, '/')}.nfo`)!));
    assert.deepEqual(strip(gen.lines), strip(ini.get(name)!.lines), name);
  }
  // the generated VerifiedIDs lines for the two Serum entries appear verbatim in the real file
  const verText = decodeText(verRaw);
  const gv = ValueFile.parse(decodeText(g.files.get('Installed/VerifiedIDs.nfo')!));
  const serumKeys = gv.lines.filter((l) => l.includes('Serum'));
  assert.equal(serumKeys.length, 2);
  for (const line of serumKeys) assert.ok(verText.includes(line + '\r\n'), line);
});

test('generated Massive X entry matches the real machine section/key (CAB-46 follow-up, minus unobservable date/size)', () => {
  const specs: PluginSpec[] = JSON.parse(readFileSync(new URL('../specs/wasm_plugins.json', import.meta.url), 'utf8')).plugins;
  const g = generateDb(specs);
  const ini = IniFile.fromBytes(iniRaw);
  const real = ini.get('Generators\\VST3\\Massive X');
  assert.ok(real, 'real machine section [Generators\\VST3\\Massive X] exists');
  // CID three-way match: real ps_file_guid == Service Center XML VST3ID == spec (REPORT.md §12.5)
  assert.equal(new ValueFile([...real.lines]).getString('ps_file_guid_0'), '{5653544E-6924-486D-6173-736976652078}');
  const drop = new Set(['ps_file_date_0', 'ps_file_size_0']);
  const strip = (lines: string[]): string[] => lines.filter((l) => !drop.has(l.slice(0, l.indexOf('=')).toLowerCase()));
  const gen = ValueFile.parse(decodeText(g.files.get('Installed/Generators/VST3/Massive X.nfo')!));
  assert.deepEqual(strip(gen.lines), strip(real.lines));
  // the generated VerifiedIDs line appears verbatim in the real file
  const gv = ValueFile.parse(decodeText(g.files.get('Installed/VerifiedIDs.nfo')!));
  const mx = gv.lines.filter((l) => l.includes('Massive X'));
  assert.deepEqual(mx, ['VST3:64:{5653544E-6924-486D-6173-736976652078}=Generators\\VST3\\Massive X.NFO']);
  assert.ok(decodeText(verRaw).includes(mx[0] + '\r\n'), mx[0]);
});
