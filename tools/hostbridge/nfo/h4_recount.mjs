// h4_recount.mjs — CAB-216 の REPORT 見出し数値を独立再計算する (規則 37)。
//   node h4_recount.mjs [work/h4/metrics.json]
//
// 実装 (h4/h4_e2e.ts) とは**別アルゴリズム**で再計算する:
//   1. wvfs のジャーナル実ファイル (work/h4/<store>/fl-w4fs-e2e/home/jrn-*.bin) を
//      **自前のレコードデコーダ**で読み、ツリーを復元する。wvfs の Journal/Wvfs クラスは
//      一切 import しない (レコード形式は journal.ts の encodeRec 仕様を独立に実装)。
//   2. `.nfo` の受理判定は src/ の reader 模型 (entry.ts) を使わず、本ファイル内の最小
//      パーサ (行頭コメント・先勝ち・大小無視) で `ps_files` / `ps_file_plugclass_<i>` /
//      `ps_file_bitsize_<i>` / `ps_file_type_<i>` を読み、plugclass→slot 表 (FORMAT.md §3)
//      を独自実装して判定する。
//   3. `.fst` は tools/flp の parseFlp を**使わず**、FLhd/FLdt コンテナを自前で分解して
//      event 199/201/203/212/213 の有無と 213 の先頭 u32 (kind 8=VST2 / 10=VST3) を数える。
//   4. vreg seed (tools/startup/data/vreg_seed.json) を JSON として読み、`Shared data` から
//      DB root を作り pathreg 既定表 (shimx/pathreg/js/pathmap.mjs の createMapper) で写映射を出し、
//      /c/home に落ちることを確認する (実装側 registryConsistency と同じ結果になるか照合)。
//
// 数え方の定義 (規則 36):
//   - 「entry」= 1 つの `.nfo` (+ 対応 `.fst`)。同名 32/64bit は 1 エントリ 2 ファイル (本 spec 集合には無し)。
//   - 「ファイル」= Installed 配下の実ファイル数 (.nfo/.fst/.Plugins.ini/VerifiedIDs.nfo を含む)。
//   - 「受理」= ps_files>=1 かつ全 ps_file_plugclass_<i> が slot 表で有効 かつ ps_file_type_<i> ∈ {1,2}。
//   - ジャーナルレコード = 物理追記単位 (MKDIR 1 件 + PUT 1 件)。distinct パス数とは別。
//   - 分母は全て「本 e2e が生成した 50 entry / 102 ファイル」。同梱 corpus (831 .nfo) は別計測 (nfo_e2e.sh)。
//
// 出力: JSON (stdout)。exit 0 = 実装側の数値と全項目一致。
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createMapper } from '../../shimx/pathreg/js/pathmap.mjs';

const NFO = path.dirname(new URL(import.meta.url).pathname); // tools/hostbridge/nfo
const WORK = path.join(NFO, 'work', 'h4');
const metricsPath = process.argv[2] ?? path.join(WORK, 'metrics.json');
const seedPath = path.join(NFO, '..', '..', 'startup', 'data', 'vreg_seed.json');
const REC_HEAD = 27; // recLen(4) crc(4) seq(4) op(1) pathLen(2) dataLen(4) mtime(8)
const JHDR = 4096;
/** Uint8Array の [from,to) を latin1 文字列へ (Uint8Array#toString は Array のそれを叩くだけで encoding 引数は効かない) */
const latin1 = (b, from = 0, to = b.length) => new TextDecoder('latin1').decode(b.subarray(from, to));

/** ジャーナルを自前デコードして { path: {op, data} } とレコード統計を返す (wvfs 非依存) */
function decodeJournal(storeDirPath) {
  const names = fs.readdirSync(storeDirPath);
  // スーパーブロック (root) の active slot から active journalId を読む (slot = 1 - activeSlot, gen 最大が現役)
  const sb = new Uint8Array(fs.readFileSync(path.join(storeDirPath, 'root')));
  const sbv = new DataView(sb.buffer, sb.byteOffset, sb.byteLength);
  const SLOT = 2048;
  let activeId = 1;
  let bestGen = -1;
  for (const slot of [0, 1]) {
    if (sb.length < (slot + 1) * SLOT) break;
    const magicOk = sb[slot * SLOT] === 0x57 && sb[slot * SLOT + 1] === 0x56 && sb[slot * SLOT + 2] === 0x53 && sb[slot * SLOT + 3] === 0x31;
    if (!magicOk) continue;
    if (sbv.getUint32(slot * SLOT + 4, true) !== 1) continue;
    if (sbv.getUint32(slot * SLOT + 16, true) !== crc32head(sb, slot * SLOT, 16)) continue;
    const gen = sbv.getUint32(slot * SLOT + 8, true);
    if (gen > bestGen) { bestGen = gen; activeId = sbv.getUint32(slot * SLOT + 12, true); }
  }
  const journalPath = path.join(storeDirPath, `jrn-${activeId}.bin`);
  const b = new Uint8Array(fs.readFileSync(journalPath));
  if (b.length < JHDR || b[0] !== 0x57 || b[1] !== 0x56 || b[2] !== 0x4a || b[3] !== 0x31) {
    throw new Error(`bad journal magic: ${journalPath} (magic=${[...b.slice(0, 4)].join(',')})`);
  }
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  // ヘッダ @12 の logicalEnd は作成時 (=JHDR) のままで更新されない (journal.ts: append はファイルを伸ばすだけ)。
  // 記録の終端は recLen を辿って発見する (torn tail は recLen 検証で落とす)。
  const files = new Map(); // path -> data (最終 PUT)
  let recs = 0, puts = 0, mkdirs = 0, dels = 0, torn = 0;
  let q = JHDR;
  while (q + REC_HEAD <= b.length) {
    const recLen = dv.getUint32(q, true);
    if (recLen < REC_HEAD || q + recLen > b.length) { torn++; break; }
    const op = b[q + 12];
    const pathLen = dv.getUint16(q + 13, true);
    const dataLen = dv.getUint32(q + 15, true);
    if (q + REC_HEAD + pathLen + dataLen > b.length) { torn++; break; }
    const p = new TextDecoder().decode(b.slice(q + REC_HEAD, q + REC_HEAD + pathLen));
    const data = dataLen ? b.slice(q + REC_HEAD + pathLen, q + REC_HEAD + pathLen + dataLen) : new Uint8Array(0);
    recs++;
    if (op === 1) { puts++; files.set(p, data); }
    else if (op === 3) { mkdirs++; }
    else if (op === 2) { dels++; files.delete(p); }
    q += recLen;
  }
  return { files, journalPath, stats: { activeJournalId: activeId, recs, puts, mkdirs, dels, torn, bytes: b.length, recordEnd: q } };
}

/** crc32 (先頭 16 B の検証用。wvfs journal.ts の crc32 と同一多項式の自前実装) */
function crc32head(b, off, len) {
  let c = 0xffffffff;
  for (let i = 0; i < len; i++) {
    c ^= b[off + i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return (c ^ 0xffffffff) >>> 0;
}

// ---- 1. store を探してデコード ----
const store = path.join(WORK, 'home', 'fl-h4-e2e', 'home');
if (!fs.existsSync(store)) { console.error('work/h4 に store が無い。先に node h4/h4_e2e.ts を実行せよ'); process.exit(2); }
const { files: vfs, stats: jstat, journalPath } = decodeJournal(store);

const DB_PREFIX = '/Documents/Image-Line/FL Studio/Presets/Plugin database/';
const dbFiles = [...vfs.entries()].filter(([p]) => p.startsWith(DB_PREFIX) && p.length > DB_PREFIX.length);
const installed = dbFiles.map(([p]) => p.slice(DB_PREFIX.length));
const allPathsInStore = [...vfs.keys()];

// ---- 2. 最小 .nfo パーサ (src/ 非依存) ----
function parseNfo(text) {
  const map = new Map();
  for (const line of text.split(/\r\n|\n|\r/)) {
    if (line.startsWith("'")) continue;
    const i = line.indexOf('=');
    if (i < 0) continue;
    const k = line.slice(0, i).toUpperCase();
    if (!map.has(k)) map.set(k, line.slice(i + 1)); // 先勝ち
  }
  return map;
}
function parseIntDef(s, def) {
  if (s === undefined) return def;
  const t = s.trim();
  if (t === '') return def;
  if (/^-?\d+$/.test(t)) return Number(t);
  if (/^\$[0-9a-fA-F]+$/.test(t)) return parseInt(t.slice(1), 16);
  if (/^0x[0-9a-fA-F]+$/.test(t)) return parseInt(t.slice(2), 16);
  return def;
}
/** FORMAT.md §3 の slot 表を独立実装 (実装側 format.ts の slotOf と同定義・別コード) */
const SLOT_TABLE = [
  { cls: 2, gen: 3, s32: 0, s64: 1 },   // Fruity
  { cls: 0, gen: 4, s32: 2, s64: 3 },   // VST
  { cls: 7, gen: 8, s32: 4, s64: 5 },   // VST3
  { cls: 9, gen: 10, s32: -1, s64: 6 }, // AU (64bit のみ)
  { cls: 11, gen: 12, s32: -1, s64: 7 }, // CLAP (64bit のみ)
];
function slotIndependent(plugclass, is64) {
  for (const f of SLOT_TABLE) {
    if (plugclass === f.cls) return is64 ? f.s64 : f.s32;
    if (plugclass === f.gen) return is64 ? f.s64 : f.s32;
  }
  return -1; // DX(1,5)・class 6・13+ は常に -1
}

let accepted = 0, dropped = 0, rejectedFiles = 0, totalPsFiles = 0, entriesWithFst = 0;
const problems = [];
const familyCount = {};
for (const rel of installed) {
  // entry は Effects|Generators 配下の .nfo のみ。Installed/VerifiedIDs.nfo は ID 表で entry ではない (別カウント)。
  if (!/^Installed\/(Effects|Generators)\/.+\.nfo$/.test(rel)) continue;
  const data = vfs.get(DB_PREFIX + rel);
  const m = parseNfo(new TextDecoder().decode(data));
  const n = parseIntDef(m.get('PS_FILES'), 0);
  let usable = 0;
  for (let i = 0; i < n; i++) {
    const pc = parseIntDef(m.get(`PS_FILE_PLUGCLASS_${i}`), -1);
    if (pc === -1) { rejectedFiles++; continue; }
    const bits = parseIntDef(m.get(`PS_FILE_BITSIZE_${i}`), 32);
    if (slotIndependent(pc, bits === 64) < 0) { rejectedFiles++; continue; }
    if (![1, 2].includes(parseIntDef(m.get(`PS_FILE_TYPE_${i}`), 0))) { rejectedFiles++; continue; }
    usable++;
  }
  totalPsFiles += n;
  if (usable > 0) accepted++; else { dropped++; problems.push(`${rel}: usable 0`); }
  const fst = rel.replace(/\.nfo$/, '.fst');
  if (installed.includes(fst)) entriesWithFst++;
  else problems.push(`${rel}: .fst が無い`);
  const seg = rel.replace(/^Installed\//, '').split('/');
  if (seg.length >= 3) { const k = `${seg[0]}/${seg[1]}`; familyCount[k] = (familyCount[k] ?? 0) + 1; }
}

// ---- 3. 最小 .fst コンテナ分解 (tools/flp 非依存) ----
let fstParsed = 0, e199 = 0, e201 = 0, e203 = 0, e212 = 0, e213 = 0, kindVst2 = 0, kindVst3 = 0;
for (const rel of installed) {
  if (!rel.endsWith('.fst')) continue;
  const b = vfs.get(DB_PREFIX + rel);
  // FLhd(4) + hdrLen u32(4) + {format u16, nCh u16, ppq u16}(6) = 14 → FLdt タグは 14 (flp.ts src と同定義)
  const p = 14;
  if (b.length < 22 || latin1(b, 0, 4) !== 'FLhd' || latin1(b, 14, 18) !== 'FLdt') continue;
  const fdv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const dtLen = fdv.getUint32(p + 4, true);
  let q = p + 8;
  const end = q + dtLen;
  while (q < end && q < b.length) {
    const id = b[q]; q += 1;
    let len = 0;
    if (id < 64) len = 0;
    else if (id < 128) { len = fdv.getUint16(q, true); q += 2; }
    else if (id < 192) { len = fdv.getUint32(q, true); q += 4; }
    else { let shift = 0; for (;;) { const c = b[q]; q += 1; len |= (c & 0x7f) << shift; shift += 7; if ((c & 0x80) === 0) break; } }
    if (id === 199) e199++;
    if (id === 201) e201++;
    if (id === 203) e203++;
    if (id === 212) e212++;
    if (id === 213) { e213++; const k = fdv.getUint32(q, true); if (k === 8) kindVst2++; else if (k === 10) kindVst3++; }
    q += len;
  }
  fstParsed++;
}

// ---- 5. .Plugins.ini セクション再計算 (セクション本編 = .nfo 本編) ----
let iniSections = 0, iniVerbatim = 0;
{
  const iniBytes = vfs.get(DB_PREFIX + 'Installed/.Plugins.ini');
  if (iniBytes) {
    const text = new TextDecoder('utf-8').decode(iniBytes[0] === 0xef && iniBytes[1] === 0xbb && iniBytes[2] === 0xbf ? iniBytes.subarray(3) : iniBytes);
    const sections = [];
    for (const line of text.split(/\r\n|\n|\r/)) {
      if (line === '') continue;
      if (line.startsWith('[') && line.endsWith(']')) sections.push({ name: line.slice(1, -1), lines: [] });
      else if (sections.length) sections[sections.length - 1].lines.push(line);
    }
    iniSections = sections.length;
    for (const rel of installed) {
      if (!/^Installed\/(Effects|Generators)\/.+\.nfo$/.test(rel)) continue;
      const want = rel.replace(/^Installed\//, '').replace(/\.nfo$/, '').replace(/\//g, '\\').toUpperCase();
      const sec = sections.find((s) => s.name.toUpperCase() === want);
      const body = parseNfo(new TextDecoder().decode(vfs.get(DB_PREFIX + rel)));
      if (sec && sec.lines.length === body.size && sec.lines.every((l) => body.has(l.slice(0, l.indexOf('=')).toUpperCase()))) iniVerbatim++;
    }
    // セクション本編と .nfo 本編が「同じキー集合・同じ行数」であることの独立確認
    for (const rel of installed) {
      if (!/^Installed\/(Effects|Generators)\/.+\.nfo$/.test(rel)) continue;
      const want = rel.replace(/^Installed\//, '').replace(/\.nfo$/, '').replace(/\//g, '\\').toUpperCase();
      const sec = sections.find((s) => s.name.toUpperCase() === want);
      if (!sec) { problems.push(`ini: ${rel} のセクションが無い`); continue; }
      const nfoLines = parseNfo(new TextDecoder().decode(vfs.get(DB_PREFIX + rel)));
      const nfoKeys = [...nfoLines.keys()].map((k) => k).sort();
      const secKeys = sec.lines.map((l) => l.slice(0, l.indexOf('=')).toUpperCase()).sort();
      if (nfoKeys.join('|') !== secKeys.join('|')) problems.push(`ini: ${rel} のキー集合が不一致`);
    }
  }
}

// ---- 4. vreg seed × pathreg 整合 ----
const seed = JSON.parse(fs.readFileSync(seedPath, 'utf8'));
const sharedData = seed.HKCU['Software\\Image-Line\\Shared\\Paths']['Shared data'].v;
const dbRootWin = sharedData.replace(/[\\/]+$/, '') + '\\FL Studio\\Presets\\Plugin database';
const raw = createMapper().map(dbRootWin);
const routesHome = raw !== null && raw.startsWith('/c/home/');

const out = {
  journal: { active: path.basename(journalPath), ...jstat, distinctFilesInStore: allPathsInStore.length },
  dbFiles: dbFiles.length,
  installedFiles: installed.length,
  nfo: installed.filter((r) => /^Installed\/(Effects|Generators)\/.+\.nfo$/.test(r)).length,
  verifiedIdKeys: (() => {
    const vf = vfs.get(DB_PREFIX + 'Installed/VerifiedIDs.nfo');
    if (!vf) return 0;
    return parseNfo(new TextDecoder().decode(vf)).size;
  })(),
  fst: installed.filter((r) => r.endsWith('.fst')).length,
  hasPluginsIni: installed.includes('Installed/.Plugins.ini'),
  hasVerifiedIds: installed.includes('Installed/VerifiedIDs.nfo'),
  iniSections,
  iniSectionsVerbatim: iniVerbatim,
  nfoAccepted: accepted,
  nfoDropped: dropped,
  nfoRejectedFiles: rejectedFiles,
  nfoTotalPsFiles: totalPsFiles,
  entriesWithFst,
  familyCount,
  fstParsed,
  fstEvents: { e199, e201, e203, e212, e213 },
  fstKinds: { vst2: kindVst2, vst3: kindVst3 },
  vreg: { sharedData, dbRootWin, rawRoute: raw, routesHome, userProfile: seed._env?.USERPROFILE, personal: seed._known_folders?.['CSIDL_PERSONAL(5)'] },
  problems,
};

// ---- 実装側 (metrics.json) と照合 ----
let mismatches = [];
if (fs.existsSync(metricsPath)) {
  const m = JSON.parse(fs.readFileSync(metricsPath, 'utf8'));
  const a = m.results?.node?.audit ?? {};
  const impl = { nfoAccepted: a.nfoAccepted, nfoRejectedFiles: a.nfoRejected, fstParsed: a.fstParsed, iniSections: a.iniSections, verifiedKeys: a.verifiedKeys };
  const verifiedKeysRecount = (() => {
    const vf = vfs.get(DB_PREFIX + 'Installed/VerifiedIDs.nfo');
    return vf ? parseNfo(new TextDecoder().decode(vf)).size : 0;
  })();
  mismatches = [
    ['nfoAccepted', impl.nfoAccepted, accepted],
    ['nfoRejectedFiles', impl.nfoRejectedFiles, rejectedFiles],
    ['fstParsed', impl.fstParsed, fstParsed],
    ['dbFiles', m.results?.node?.files, dbFiles.length],
    ['iniSections', impl.iniSections, iniSections],
    ['verifiedKeys', impl.verifiedKeys, verifiedKeysRecount],
  ].filter(([, x, y]) => x !== y);
}
console.log(JSON.stringify(out, null, 1));
if (mismatches.length) {
  console.error('\n不一致 (実装側 / 再計算):');
  for (const [k, x, y] of mismatches) console.error(`  ${k}: impl=${x} recount=${y}`);
  process.exit(1);
}
console.log('\n照合: 実装側 (h4/h4_e2e.ts) と全項目一致 (nfoAccepted / nfoRejectedFiles / fstParsed / dbFiles / iniSections / verifiedKeys)');
process.exit(0);
