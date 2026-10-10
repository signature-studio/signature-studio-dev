// One-command CAB-46 follow-up check (Massive X VST3 CID 突合 + spec 追加の実機照合):
//   node analysis/mx_check.mjs
// Exit 0 = all checks PASS. Evidence: evidence/real_machine/{.Plugins.ini,VerifiedIDs.nfo} (committed) +
// tools/targets/massivex/work/ (gitignored, optional at runtime): installer inventory (files.json), extracted
// single-file module (VST3/Massive X.vst3, 95,356,824 B), Service Center XML (VST3ID/PluginID/UPID).
// moduleinfo.json: NI ships NONE (not in the 11,602-file installer payload, not embedded in the PE — only the
// Steinberg::ModuleInfoLib RTTI name). The CID is therefore pinned by the real machine's own FL scan
// (.Plugins.ini ps_file_guid) == Service Center XML == the GetPluginFactory PluginID derivation. REPORT.md §12.5.
import { readFileSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const dir = new URL('../evidence/real_machine/', import.meta.url);
const mxWork = '../../../targets/massivex/work/';
const checks = [];
const ok = (name, cond, detail = '') => { checks.push({ name, ok: !!cond, detail }); if (!cond) process.exitCode = 1; };

// ---------- parse the real .Plugins.ini ----------
const iniText = readFileSync(new URL('.Plugins.ini', dir), 'utf8').slice(1); // drop BOM
const secs = new Map();
for (const block of iniText.split('\r\n\r\n')) {
  const lines = block.split('\r\n');
  const head = lines.shift();
  if (head?.startsWith('[') && head.endsWith(']')) secs.set(head.slice(1, -1), lines);
}
const field = (lines, k) => lines.find((l) => l.toLowerCase().startsWith(k.toLowerCase() + '='))?.split('=').slice(1).join('=');
const SEC = 'Generators\\VST3\\Massive X';
const mx = secs.get(SEC);
ok('ini: real section [Generators\\VST3\\Massive X] exists (FL scanned the installed module)', !!mx);
const real = {
  name: mx && field(mx, 'ps_name'), filename: mx && field(mx, 'ps_file_filename_0'),
  plugclass: mx && field(mx, 'ps_file_plugclass_0'), type: mx && field(mx, 'ps_file_type_0'),
  bits: mx && field(mx, 'ps_file_bitsize_0'), arch: mx && field(mx, 'ps_file_arch_0'),
  guid: mx && field(mx, 'ps_file_guid_0'), size: mx && Number(field(mx, 'ps_file_size_0')),
  scanflags: mx && field(mx, 'ps_file_scanflags_0'), vendor: mx && field(mx, 'ps_file_vendorname_0'),
  category: mx && field(mx, 'ps_file_category_0'),
};
ok('ini: plugclass=8 (VST3 gen) / type=2 / bits=64 / arch=Intel / scanflags=1',
  real.plugclass === '8' && real.type === '2' && real.bits === '64' && real.arch === 'Intel' && real.scanflags === '1',
  `class ${real.plugclass} type ${real.type} bits ${real.bits} arch ${real.arch} sf ${real.scanflags}`);
ok('ini: vendor "Native Instruments" / category "Instrument|Synth" (real scanner values)',
  real.vendor === 'Native Instruments' && real.category === 'Instrument|Synth', `${real.vendor} / ${real.category}`);

// ---------- CID: 3-way + NI FUID rule ----------
const CID_TEXT = '{5653544E-6924-486D-6173-736976652078}'; // CAB-46 VST3ID / Service Center XML (case-insensitive cmp)
const dashed = (hex) => `{${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}}`.toUpperCase();
// NI FUID rule (REPORT.md §12.5): ASCII "VST" + PluginID big-endian bytes + lower(name), truncated to 16 bytes.
// GetPluginFactory (0x18000a870) holds the immediate `mov edx, 0x4e692448` (CAB-46 §4, re-verified by disassembly).
const PLUGIN_ID = 0x4e692448;
const fuid = Buffer.from('VST' + Buffer.from([(PLUGIN_ID >>> 24) & 0xff, (PLUGIN_ID >>> 16) & 0xff, (PLUGIN_ID >>> 8) & 0xff, PLUGIN_ID & 0xff]).toString('latin1') + 'massive x', 'latin1').subarray(0, 16);
ok('cid: NI FUID rule "VST"+BE32(0x4e692448)+"massive x" == real ps_file_guid',
  dashed(fuid.toString('hex')) === (real.guid ?? '').toUpperCase(),
  `${dashed(fuid.toString('hex'))} vs ${real.guid}`);
// Windows GUID memory layout bytes of the CID text (= what the .fst record 52 / tuidFromHex hold):
// text-order "VSTNi$Hmassive x" → Data1/2/3 little-endian → "NTSV$iHmassive x"
const winLayout = Buffer.from([fuid[3], fuid[2], fuid[1], fuid[0], fuid[5], fuid[4], fuid[7], fuid[6], ...fuid.slice(8)]);
ok('cid: raw 16B text order == "VSTNi$Hmassive x" and Windows-layout hex == 4e54535624696d486173736976652078 (CAB-46 §4 生値)',
  fuid.toString('latin1') === 'VSTNi$Hmassive x' && winLayout.toString('hex') === '4e54535624696d486173736976652078',
  `${fuid.toString('latin1')} / ${winLayout.toString('hex')}`);
ok('cid: real ps_file_guid == {5653544E-6924-486D-6173-736976652078}', (real.guid ?? '').toUpperCase() === CID_TEXT, real.guid ?? '');
// Service Center XML (installer payload) — optional, gitignored work/
const xmlPath = here(mxWork + 'extracted/Native Instruments/Service Center/Massive X.xml');
if (existsSync(xmlPath)) {
  const xml = readFileSync(xmlPath, 'utf8');
  const vst3id = /<VST3ID>([^<]+)<\/VST3ID>/.exec(xml)?.[1];
  const pid = /<PluginID>([^<]+)<\/PluginID>/.exec(xml)?.[1];
  const upid = /<UPID>([^<]+)<\/UPID>/.exec(xml)?.[1];
  ok('cid: Service Center XML VST3ID == real ps_file_guid (moduleinfo.json-equivalent, case/brace-insensitive)',
    !!vst3id && vst3id.toUpperCase() === CID_TEXT.slice(1, -1), vst3id ?? 'missing');
  ok('cid: Service Center XML PluginID == 0x4e692448 (GetPluginFactory immediate) and SNPID/Name present',
    pid === '0x4e692448' && /<SNPID>MXE<\/SNPID>/.test(xml) && /<Name>Massive X<\/Name>/.test(xml), `${pid}`);
  ok('cid: UPID is the licensing product id, NOT the CID (41ce4ac2-… ≠ 5653544E-…)',
    !!upid && upid !== CID_TEXT.slice(1, -1) && upid === '41ce4ac2-34f7-469b-beb8-59a8ad7a8a67', upid ?? 'missing');
  ok('compat: real section carries no ps_compatibility (Serum 2 spec 踏襲 — UPID/旧IDの別名登録は不要)',
    mx && !mx.some((l) => l.toLowerCase().startsWith('ps_compatibility_')));
}

// ---------- moduleinfo.json 不在 + single-file module 実配置 (installer 側, optional) ----------
const filesJson = here(mxWork + 'files.json');
if (existsSync(filesJson)) {
  const inv = JSON.parse(readFileSync(filesJson, 'utf8'));
  const vst3 = inv.filter((e) => /\.vst3$/i.test(e.dst));
  ok('installer: exactly one .vst3, dst = {cf}\\VST3\\Massive X.vst3 (単一ファイルモジュール形 — Contents 無し)',
    vst3.length === 1 && vst3[0].dst === '{cf}\\VST3\\Massive X.vst3', JSON.stringify(vst3.map((v) => v.dst)));
  ok('installer: no moduleinfo.json in the 11,602-file payload (VST3 標準の CID 源は本製品は同梱せず)',
    inv.length === 11602 && !inv.some((e) => /oduleinfo/i.test(e.dst + e.src)), `${inv.length} files`);
}
const pePath = here(mxWork + 'extracted/VST3/Massive X.vst3');
if (existsSync(pePath)) {
  const pe = readFileSync(pePath);
  ok('installer: extracted Massive X.vst3 = PE32+ single FILE, 95,356,824 B == real ini ps_file_size_0',
    pe.length === 95356824 && pe[0] === 0x4d && pe[1] === 0x5a && pe.length === real.size,
    `file ${pe.length} vs ini ${real.size}`);
  const peStr = pe.toString('latin1');
  const hits = [...peStr.matchAll(/moduleinfo/gi)].length; // only the Steinberg::ModuleInfoLib RTTI name
  ok('installer: PE embeds no moduleinfo.json (case-insensitive "moduleinfo" hits = 1 = ModuleInfoLib RTTI のみ)',
    !peStr.includes('moduleinfo.json') && hits === 1, `${hits} hit(s)`);
}
ok('path: real ps_file_filename = module-FILE form C:\\Program Files\\Common Files\\VST3\\Massive X.vst3 (no \\Contents\\, §12.1 規則の単一ファイル形)',
  real.filename === 'C:\\Program Files\\Common Files\\VST3\\Massive X.vst3', real.filename ?? '');
const vst2dll = here(mxWork + 'extracted/Native Instruments/Massive X.dll');
if (existsSync(vst2dll)) {
  ok('record: VST2 Massive X.dll 95,249,816 B exists but stays OUT of the spec (VST3 のみ — Serum 2 踏襲, REPORT 記録用)',
    statSync(vst2dll).size === 95249816, String(statSync(vst2dll).size));
}

// ---------- generated DB vs real machine ----------
const { generateDb } = await import('../src/generate.ts');
const specs = JSON.parse(readFileSync(here('../specs/wasm_plugins.json'), 'utf8')).plugins;
const spec = specs.find((s) => s.name === 'Massive X');
ok('spec: Massive X entry present, vst3/generator (class 8), guid text == CID, path == real filename',
  !!spec && spec.format === 'vst3' && spec.kind === 'generator' &&
  dashed(spec.guid).toUpperCase() === CID_TEXT && spec.path === real.filename,
  JSON.stringify(spec ?? null));
const g = generateDb(specs);
const linesOf = (rel) => new TextDecoder().decode(g.files.get(rel)).split('\r\n').filter((l, i, a) => !(i === a.length - 1 && l === ''));
const drop = new Set(['ps_file_date_0', 'ps_file_size_0']);
const strip = (ls) => ls.filter((l) => !drop.has(l.slice(0, l.indexOf('=')).toLowerCase()));
ok('generate: gen section == real "Generators\\VST3\\Massive X" (incl. filename/guid/vendor/category, minus date/size)',
  JSON.stringify(strip(linesOf('Installed/Generators/VST3/Massive X.nfo'))) === JSON.stringify(strip(mx)));
const verText = readFileSync(new URL('VerifiedIDs.nfo', dir), 'utf8');
const expectKey = `VST3:64:${CID_TEXT}=Generators\\VST3\\Massive X.NFO`;
ok('verifiedids: generated key appears verbatim in the real VerifiedIDs.nfo', verText.includes(expectKey + '\r\n'), expectKey);

console.log(JSON.stringify({
  cab46mx: {
    section: SEC, cid: CID_TEXT, pluginId: '0x4e692448', snpid: 'MXE',
    filename: real.filename, size: real.size, vendor: real.vendor, category: real.category,
    moduleinfoJson: 'not shipped (installer 11,602 files / PE: ModuleInfoLib RTTI のみ) — 実機 ini + XML + 即値導出の三重突合で代替',
    checks: checks.length, failed: checks.filter((c) => !c.ok).length,
  },
}, null, 1));
for (const c of checks) if (!c.ok) console.error(`FAIL: ${c.name} — ${c.detail}`);
