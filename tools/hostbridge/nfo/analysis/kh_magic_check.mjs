// One-command CAB-218 check (H11 VST3 path rule + KH VST2 magic 実測差し替え + VerifiedIDs decimal 表記):
//   node analysis/kh_magic_check.mjs
// Exit 0 = all checks PASS. Evidence: evidence/real_machine/{.Plugins.ini,VerifiedIDs.nfo} + installers/targets
// (OTT.exe / Serum2.exe / Kilohearts winpkg+macpkg product_index.json). Numbers quoted in REPORT.md §12.
import { readFileSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const dir = new URL('../evidence/real_machine/', import.meta.url);
const checks = [];
const ok = (name, cond, detail = '') => { checks.push({ name, ok: !!cond, detail }); if (!cond) process.exitCode = 1; };

// ---------- parse the real .Plugins.ini into sections ----------
const iniText = readFileSync(new URL('.Plugins.ini', dir), 'utf8').slice(1); // drop BOM
const secs = new Map();
for (const block of iniText.split('\r\n\r\n')) {
  const lines = block.split('\r\n');
  const head = lines.shift();
  if (head?.startsWith('[') && head.endsWith(']')) secs.set(head.slice(1, -1), lines);
}
const field = (lines, k) => lines.find((l) => l.toLowerCase().startsWith(k.toLowerCase() + '='))?.split('=').slice(1).join('=');

// VST2 files (plugclass 0/4) carrying a magic, per section
const vst2 = [];
for (const [name, lines] of secs) {
  const n = Number(field(lines, 'ps_files') || 0);
  for (let i = 0; i < n; i++) {
    if (field(lines, `ps_file_plugclass_${i}`) !== '0' && field(lines, `ps_file_plugclass_${i}`) !== '4') continue;
    const magic = field(lines, `ps_file_magic_${i}`);
    if (magic === undefined) continue;
    vst2.push({ section: name, magic: Number(magic) | 0, name: field(lines, `ps_file_name_${i}`) || field(lines, 'ps_name'),
      vendor: field(lines, `ps_file_vendorname_${i}`) ?? '', category: field(lines, `ps_file_category_${i}`) ?? '',
      guid: field(lines, `ps_file_guid_${i}`) ?? '', filename: field(lines, `ps_file_filename_${i}`) ?? '' });
  }
}
ok('ini: 406 sections parsed', secs.size === 406, String(secs.size));
ok('ini: VST2 magic-bearing files = 64', vst2.length === 64, String(vst2.length));
const inEffectsVST = vst2.filter((v) => v.section.startsWith('Effects\\VST\\'));
ok('ini: Effects\\VST magic sections = 55 (the "55 種" of CAB-219)', inEffectsVST.length === 55, String(inEffectsVST.length));

// ---------- magic values are 4 printable chars (BE) when read as signed int32 ----------
const magic4 = (m) => { const b = [m >>> 24, (m >>> 16) & 0xff, (m >>> 8) & 0xff, m & 0xff]; return b.map((x) => String.fromCharCode(x)).join(''); };
const ascii = vst2.filter((v) => /^[\x20-\x7e]{4}$/.test(magic4(v.magic)));
ok('ini: all 64 VST2 magics decode to 4 printable ASCII chars (BE)', ascii.length === 64, `${ascii.length}/64`);

// ---------- KH subset vs product_index ids (CAB-46 領域) ----------
const kh = vst2.filter((v) => v.vendor === 'Kilohearts' || v.section === 'Effects\\VST\\Fresh Air');
ok('ini: KH-family VST2 entries with magic = 46', kh.length === 46, String(kh.length));
let idxHits = 0, idxMiss = [];
for (const pkg of ['winpkg', 'macpkg']) {
  const p = `../../../targets/kilohearts/work/${pkg}/product_index.json`;
  if (!existsSync(here(p))) continue;
  const idx = new Map(JSON.parse(readFileSync(here(p), 'utf8')).plugins.map((x) => [x.fileName, x.id]));
  let hit = 0;
  for (const v of kh) {
    const id = idx.get(v.name);
    if (id !== undefined && magic4(v.magic) === id) hit++; else if (id !== undefined) idxMiss.push(`${pkg}:${v.name}`);
  }
  if (pkg === 'winpkg') ok('kilohearts: product_index id == real magic (winpkg, 45 KH products + Fresh Air FrAr via targets)', hit === 45, `${hit}/45 ${idxMiss.join(',')}`);
  else ok('kilohearts: product_index id == real magic (macpkg)', hit === 45, `${hit}/45`);
  idxHits += hit;
}
ok('kilohearts: Fresh Air magic == FrAr (1181892978)', kh.find((v) => v.name === 'Fresh Air')?.magic === 1181892978);
ok('kilohearts: real VST2 categories = Effect(44)/Synth(1 Phase Plant) + Fresh Air Effect',
  kh.filter((v) => v.category === 'Effect').length === 45 && kh.find((v) => v.name === 'Phase Plant')?.category === 'Synth',
  JSON.stringify([...new Set(kh.map((v) => `${v.category}:${v.vendor}`))]));

// ---------- VerifiedIDs VST id representation (signed decimal) ----------
const verLines = readFileSync(new URL('VerifiedIDs.nfo', dir), 'utf8').split('\r\n');
const vstKeys = verLines.filter((l) => /^VST:(32|64):-?\d+=/.test(l));
const magics = new Set(vst2.map((v) => v.magic));
ok('verifiedids: 64 VST keys', vstKeys.length === 64, String(vstKeys.length));
ok('verifiedids: every VST key id == a ps_file_magic as SIGNED decimal (64/64)',
  vstKeys.every((l) => magics.has(Number(l.split('=', 1)[0].split(':')[2]) | 0)));
const negatives = vstKeys.filter((l) => l.split(':', 3)[2].startsWith('-'));
ok('verifiedids: no real magic reaches 2^31 (all keys positive; ≥2^31 負値表記は実機例無し → REPORT 推定)',
  negatives.length === 0 && Math.max(...magics) < 2 ** 31, `max magic ${Math.max(...magics)}`);

// ---------- VST3 ps_file_filename form rule (H11 / CAB-218) ----------
const vst3fn = [];
for (const [name, lines] of secs) {
  const n = Number(field(lines, 'ps_files') || 0);
  for (let i = 0; i < n; i++) {
    if (field(lines, `ps_file_plugclass_${i}`) !== '7' && field(lines, `ps_file_plugclass_${i}`) !== '8') continue;
    const fn = field(lines, `ps_file_filename_${i}`);
    if (fn) vst3fn.push({ section: name, fn, size: Number(field(lines, `ps_file_size_${i}`) ?? 0) });
  }
}
const inner = vst3fn.filter((v) => /\\Contents\\/i.test(v.fn));
const plain = vst3fn.filter((v) => !/\\Contents\\/i.test(v.fn) && /\.vst3$/i.test(v.fn));
ok('ini: VST3 filenames = inner-binary form 15 + module-file form 164 (両形とも実在, 計 179)',
  inner.length === 15 && plain.length === 164, `${inner.length}+${plain.length}/${vst3fn.length}`);
// single-file proof: OTT/kHs sizes match the actual installer payloads on disk
const ott = vst3fn.find((v) => v.section === 'Effects\\VST3\\OTT');
const ottInstaller = '/home/ubuntu/ダウンロード/Install_Xfer_OTT_137.exe';
if (existsSync(ottInstaller) && ott) {
  const { execSync } = await import('node:child_process');
  // NSIS -slt leaves Size empty; stream the file out and count bytes (the installed single-file module)
  const buf = execSync(`7z e -so "${ottInstaller}" "C:/Program Files/Common Files/VST3/OTT.vst3"`, { maxBuffer: 64 * 1024 * 1024 });
  ok('h11: real OTT.vst3 = single FILE (ini ps_file_size == installer file size)',
    buf.length === ott.size, `ini ${ott.size} vs installer ${buf.length}`);
}
const gain = vst3fn.find((v) => v.section === 'Effects\\VST3\\kHs Gain');
const gainFile = here('../../../targets/kilohearts/work/winpkg/kHs Gain.vst3_64');
if (existsSync(gainFile) && gain) {
  ok('h11: real kHs Gain.vst3 = single FILE (ini size == winpkg single-file module 247,296 B)',
    statSync(gainFile).size === gain.size, `ini ${gain.size} vs winpkg ${statSync(gainFile).size}`);
}
const serum = vst3fn.filter((v) => v.section.includes('Serum 2'));
const serumInner = serum.every((v) => /Serum2\.vst3\\Contents\\x86_64-win\\Serum2\.vst3$/i.test(v.fn));
ok('h11: real Serum 2 (both classes) records the bundle INNER binary path', serumInner && serum.length === 2,
  serum.map((v) => v.fn).join(' | '));
const serumBin = here('../../../targets/serum2/work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3');
if (existsSync(serumBin)) {
  const fx = serum.find((v) => v.section.includes('FX'));
  ok('h11: Serum 2 FX ini size == 2.1.5 installer inner binary (19,236,864 B)', fx && statSync(serumBin).size === fx.size,
    `ini ${fx?.size} vs installer ${statSync(serumBin).size}`);
}

// ---------- generated DB vs real machine (KH + Serum 2 filename-inclusive) ----------
const { generateDb } = await import('../src/generate.ts');
const specs = JSON.parse(readFileSync(here('../specs/wasm_plugins.json'), 'utf8')).plugins;
// KH expansion (same rule as cli/gen.ts) from the real-measured pairs
for (const v of kh) {
  if (v.name === 'Fresh Air') continue; // already in specs
  specs.push({ name: v.name, vendor: 'Kilohearts', format: 'vst2', kind: v.name === 'Phase Plant' ? 'generator' : 'effect',
    magic: magic4(v.magic), path: `C:\\Program Files\\Common Files\\VST2\\Kilohearts\\${v.name}.dll`, category: v.category });
}
const g = generateDb(specs);
const linesOf = (rel) => new TextDecoder().decode(g.files.get(rel)).split('\r\n').filter((l, i, a) => !(i === a.length - 1 && l === ''));
let khMatch = 0, khDiff = [];
for (const v of kh) {
  const sub = v.section.replace(/\\/g, '/');
  const gen = linesOf(`Installed/${sub}.nfo`);
  const get = (k) => gen.find((l) => l.toLowerCase().startsWith(k.toLowerCase() + '='))?.split('=').slice(1).join('=');
  const expect = {
    ps_name: v.name, ps_file_name_0: v.name, ps_file_magic_0: String(v.magic), ps_file_guid_0: v.guid,
    ps_file_plugclass_0: v.name === 'Phase Plant' ? '4' : '0', ps_file_type_0: v.name === 'Phase Plant' ? '2' : '1',
    ps_file_bitsize_0: '64', ps_file_arch_0: 'Intel', ps_file_vendorname_0: v.vendor, ps_file_category_0: v.category,
  };
  const bad = Object.entries(expect).filter(([k, val]) => (get(k) ?? '') !== val).map(([k, val]) => `${k}: got '${get(k)}' want '${val}'`);
  if (bad.length === 0) khMatch++;
  else khDiff.push(`${v.name} [${bad.slice(0, 2).join('; ')}]`);
}
ok('generate: KH entries match the real sections on name/magic/guid/class/type/bits/arch/vendor/category (46/46)',
  khMatch === 46, `${khMatch}/46 ${khDiff.join(',')}`);
for (const name of ['Generators\\VST3\\Serum 2', 'Effects\\VST3\\Serum 2 FX']) {
  const real = secs.get(name);
  const drop = new Set(['ps_file_date_0', 'ps_file_size_0']);
  const strip = (ls) => ls.filter((l) => !drop.has(l.slice(0, l.indexOf('=')).toLowerCase()));
  ok(`generate: gen section == real "${name}" (incl. filename, minus date/size)`,
    JSON.stringify(strip(linesOf(`Installed/${name.replace(/\\/g, '/')}.nfo`))) === JSON.stringify(strip(real)));
}

console.log(JSON.stringify({
  cab218: {
    vst2MagicFiles: vst2.length, effectsVstMagicSections: inEffectsVST.length, khFamily: kh.length,
    khIndexMatch: `${idxHits}/90 (winpkg+macpkg 各45/45, +Fresh Air FrAr via targets)`,
    verifiedIdsVst: `${vstKeys.length}/64 signed decimal, negative keys ${negatives.length} (max magic ${Math.max(...magics)} < 2^31)`,
    vst3FilenameForms: { innerBinary: inner.length, moduleFile: plain.length },
    generatedKhMatch: `${khMatch}/46`, checks: checks.length, failed: checks.filter((c) => !c.ok).length,
  },
}, null, 1));
for (const c of checks) if (!c.ok) console.error(`FAIL: ${c.name} — ${c.detail}`);
