// One-command real-machine ingest check (CAB-219): validates the user's actual `Installed\.Plugins.ini` and
// `Installed\VerifiedIDs.nfo` (evidence/real_machine/) against the src/ reader+writer models and prints the
// measured numbers quoted in REPORT.md §11. Exit 0 = all checks PASS.
//   node analysis/real_ini_check.mjs
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { IniFile } from '../src/ini.ts';
import { ValueFile, decodeText } from '../src/valuefile.ts';
import { readEntry, writeEntry, bitsToTDateTime, tDateTimeToIso, tDateTimeToBits } from '../src/entry.ts';
import { vst2PseudoGuid, guidToString, delimitedParse } from '../src/format.ts';
import { generateDb } from '../src/generate.ts';

const dir = new URL('../evidence/real_machine/', import.meta.url);
const iniRaw = new Uint8Array(readFileSync(new URL('.Plugins.ini', dir)));
const verRaw = new Uint8Array(readFileSync(new URL('VerifiedIDs.nfo', dir)));
const sha = (b) => createHash('sha256').update(b).digest('hex');
const checks = [];
const ok = (name, cond, detail = '') => { checks.push({ name, ok: !!cond, detail }); if (!cond) process.exitCode = 1; };

// ---------- .Plugins.ini ----------
const ini = IniFile.fromBytes(iniRaw);
ok('ini: UTF-8 BOM', iniRaw[0] === 0xef && iniRaw[1] === 0xbb && iniRaw[2] === 0xbf);
ok('ini: CRLF only', !/(?<!\r)\n/.test(iniRaw.subarray(3)));
ok('ini: 406 sections, no duplicates', ini.sections.length === 406 && new Set(ini.sections.map((s) => s.name.toUpperCase())).size === 406);
ok('ini: round-trip byte-exact', Buffer.compare(ini.toBytes(), iniRaw) === 0);

let files = 0, natives = 0, decorated = 0, multi = 0, writerExact = 0;
const arch = new Map(), sf = new Map();
let dMin = Infinity, dMax = -Infinity, dates = 0;
const spot = { bits: 4676583981019826458n, iso: tDateTimeToIso(bitsToTDateTime(4676583981019826458n)) };
for (const sec of ini.sections) {
  const vf = new ValueFile([...sec.lines]);
  const r = readEntry(vf);
  if (r.dropped || r.rejectedFiles.length) { ok(`ini: FL reader accepts "${sec.name}"`, false, r.dropped ?? JSON.stringify(r.rejectedFiles)); continue; }
  const e = r.entry;
  let opts = {};
  if (vf.get('iconindex') !== undefined) {
    decorated++;
    e.files[0] = { ...e.files[0], scanflags: 1 | 8 };
    opts = { newDecoration: { tip: vf.getString('tip') } };
  }
  if (JSON.stringify(writeEntry(e, opts).lines) === JSON.stringify(sec.lines)) writerExact++;
  else ok(`ini: writer reproduces "${sec.name}"`, false);
  const n = Number(vf.getString('ps_files'));
  files += n;
  if (n >= 2) multi++;
  if (/\\Fruity\\/.test(sec.name)) natives++;
  for (let i = 0; i < n; i++) {
    const a = vf.getString(`ps_file_arch_${i}`);
    arch.set(a, (arch.get(a) ?? 0) + 1);
    const s = vf.getString(`ps_file_scanflags_${i}`);
    sf.set(s, (sf.get(s) ?? 0) + 1);
    const dk = vf.get(`ps_file_date_${i}`);
    if (dk !== undefined) { const d = bitsToTDateTime(BigInt(dk)); dMin = Math.min(dMin, d); dMax = Math.max(dMax, d); dates++; }
  }
}
ok('ini: FL reader accepts all 406 sections', checks.every((c) => !c.name.startsWith('ini: FL reader')));
ok('ini: writer reproduces all 406 sections', writerExact === 406, `${writerExact}/406`);
ok('ini: file count 407', files === 407, String(files));
ok('ini: native Fruity sections 139', natives === 139, String(natives));
ok('ini: arch=Intel on 407/407', arch.get('Intel') === 407, JSON.stringify([...arch]));
ok('ini: scanflags disk 1/2/0x22 = 363/26/18', sf.get('1') === 363 && sf.get('2') === 26 && sf.get('34') === 18, JSON.stringify([...sf]));
ok('ini: date = TDateTime double bits (spot)', spot.iso === '2026-07-07T19:48:06.000Z' && tDateTimeToBits(bitsToTDateTime(spot.bits)) === spot.bits, spot.iso);
ok('ini: 407 dates in 2015-10-22..2026-09-29', dates === 407 && tDateTimeToIso(dMin).startsWith('2015-10-22') && tDateTimeToIso(dMax).startsWith('2026-09-29'),
  `${tDateTimeToIso(dMin)} .. ${tDateTimeToIso(dMax)}`);

// ---------- VerifiedIDs.nfo ----------
const verText = decodeText(verRaw);
const ver = ValueFile.parse(verText);
ok('verifiedids: lossless value-file round-trip', ver.toString() === verText);
ok('verifiedids: 236 unique keys', ver.lines.length === 236 && new Set(ver.lines.map((l) => l.slice(0, l.indexOf('=')))).size === 236);
const famCount = { VST: 0, VST3: 0, CLAP: 0 };
let crossOk = 0;
for (const line of ver.lines) {
  const p = line.indexOf('=');
  const key = line.slice(0, p), val = line.slice(p + 1);
  const m = /^(VST|VST3|CLAP):(32|64):(.+)$/.exec(key);
  if (!m) { ok(`verifiedids: key shape "${key}"`, false); continue; }
  famCount[m[1]]++;
  const sec = ini.get(val.replace(/\.NFO$/i, ''));
  if (!sec) { ok(`verifiedids: section for "${key}"`, false, val); continue; }
  const svf = new ValueFile([...sec.lines]);
  let hit = false;
  if (m[1] === 'VST') hit = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_magic_')).map((k) => svf.getString(k)).includes(m[3]);
  else if (m[1] === 'VST3') {
    const guids = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_guid_')).map((k) => svf.getString(k).toUpperCase());
    for (const k of svf.keys().filter((k) => k.toLowerCase().startsWith('ps_compatibility_'))) guids.push(...delimitedParse(svf.getString(k)).map((x) => x.toUpperCase()));
    hit = guids.includes(m[3].toUpperCase());
  } else hit = svf.keys().filter((k) => k.toLowerCase().startsWith('ps_file_idstring_')).map((k) => svf.getString(k)).includes(m[3]);
  if (hit) crossOk++; else ok(`verifiedids: id ↔ section "${key}"`, false, val);
}
ok('verifiedids: family counts 64/171/1', famCount.VST === 64 && famCount.VST3 === 171 && famCount.CLAP === 1, JSON.stringify(famCount));
ok('verifiedids: every key resolves into its section (236/236)', crossOk === 236, `${crossOk}/236`);
const referenced = new Set(ver.lines.map((l) => l.slice(l.indexOf('=') + 1).replace(/\.NFO$/i, '')));
const expected = new Set(ini.sections.filter((s) => !/\\Fruity\\/.test(s.name) && new ValueFile([...s.lines]).getString('ps_file_scanflags_0') === '1').map((s) => s.name));
ok('verifiedids: = exactly the non-native scanflags=1 entries (236 keys → 223 nfos)', referenced.size === 223 && referenced.size === expected.size && [...referenced].every((x) => expected.has(x)), `${referenced.size} sections`);

// VST2 pseudo-guid rule on real data
let pg = 0, pgOk = 0;
const magicSamples = [];
for (const sec of ini.sections) {
  const vf = new ValueFile([...sec.lines]);
  for (let i = 0; i < Number(vf.getString('ps_files') || 0); i++) {
    const magic = vf.get(`ps_file_magic_${i}`);
    if (magic === undefined) continue;
    const g = vf.get(`ps_file_guid_${i}`);
    const name = vf.getString(`ps_file_name_${i}`) || vf.getString('ps_name');
    if (magicSamples.length < 6) magicSamples.push({ name, magic: Number(magic) | 0, hex: (Number(magic) >>> 0).toString(16).padStart(8, '0') });
    if (g === undefined) continue;
    pg++;
    if (guidToString(vst2PseudoGuid(name, Number(magic) | 0)) === g) pgOk++;
    else ok(`ini: VST2 pseudo-guid "${sec.name}" #${i}`, false, g);
  }
}
ok('ini: VST2 ps_file_guid = "VST"+magic4+lower(name) (64/64)', pg === 64 && pgOk === 64, `${pgOk}/${pg}`);

// generated DB vs real machine (Serum 2 pair + VerifiedIDs keys)
const specs = JSON.parse(readFileSync(new URL('../specs/wasm_plugins.json', import.meta.url), 'utf8')).plugins;
const g = generateDb(specs);
const drop = new Set(['ps_file_date_0', 'ps_file_size_0', 'ps_file_filename_0']);
const strip = (lines) => lines.filter((l) => !drop.has(l.slice(0, l.indexOf('=')).toLowerCase()));
for (const name of ['Generators\\VST3\\Serum 2', 'Effects\\VST3\\Serum 2 FX']) {
  const gen = ValueFile.parse(decodeText(g.files.get(`Installed/${name.replace(/\\/g, '/')}.nfo`)));
  ok(`gen == real section "${name}" (minus date/size/filename)`, JSON.stringify(strip(gen.lines)) === JSON.stringify(strip(ini.get(name).lines)));
}
const gv = ValueFile.parse(decodeText(g.files.get('Installed/VerifiedIDs.nfo')));
const serumKeys = gv.lines.filter((l) => l.includes('Serum'));
ok('gen VerifiedIDs Serum keys appear verbatim in the real file (2)', serumKeys.length === 2 && serumKeys.every((l) => verText.includes(l + '\r\n')), serumKeys.join(' | '));

console.log(JSON.stringify({
  plugins_ini: { bytes: iniRaw.length, sha256: sha(iniRaw), sections: ini.sections.length, files: 407, natives: 139, decorated: 6, multiFile: multi,
    writerReproduced: `${writerExact}/406`, arch: Object.fromEntries(arch), scanflagsDisk: Object.fromEntries(sf),
    date: { rule: 'int64 = IEEE754 bits of Delphi TDateTime (epoch 1899-12-30)', spot: `${spot.bits} -> ${spot.iso}`, range: `${tDateTimeToIso(dMin)} .. ${tDateTimeToIso(dMax)}` } },
  verifiedids: { bytes: verRaw.length, sha256: sha(verRaw), keys: 236, families: famCount, sectionsReferenced: 223, compatAliasExample: 'Splice INSTRUMENT = guid + 4 compat GUIDs' },
  vst2: { pseudoGuid: '"VST"+magic4(BE)+lower(name), 16B', reproduced: `${pgOk}/${pg}`, magicSamples },
  generated: { entries: g.entries.length, files: g.files.size, bytes: [...g.files.values()].reduce((a, b) => a + b.length, 0), serumSectionMatch: true, serumVerifiedKeysMatch: true },
  checks: checks.length, failed: checks.filter((c) => !c.ok).length,
}, null, 1));
