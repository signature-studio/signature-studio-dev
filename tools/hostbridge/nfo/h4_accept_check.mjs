// h4_accept_check.mjs — CAB-216 (HB-H4') 検収担当の独立再計算 (SUBAGENT_RULES 規則 37)。
//   node h4_accept_check.mjs            ← 先に実行 (work/h4-accept/cli-out を生成する)
//   node h4_accept_chrome.mjs work/h4/chrome-profiles/h4-e2e-XXX work/h4-accept/cli-out
//
// 実装側 (h4/h4_e2e.ts / virtual_fs_seed.ts) とは**別アルゴリズム**:
//   1. 生成の基準は `cli/gen.ts` を**別プロセスで実行して実ディスクに書いた木** (h4/specs.ts の spec
//      集合は import しない。集計は fs.readdirSync(withFileTypes) の再帰 walk)。
//   2. Win パス → 仮想 FS パスの写 Mapping は pathreg の **JS ミラー**
//      (tools/shimx/pathreg/js/pathmap.mjs の createMapper) を使い `/c/home` 接頭辞を自前で strip する。
//      pathlink.ts の createPathRouter().route() は**本編では使わない** (末尾で cross-check としてのみ呼ぶ)。
//   3. wvfs への書込は seedPluginDb を呼ばず、自前の mkdirpSync + writeFileSync ループ。
//   4. `.nfo` 受理判定は**正規表現** (`^key=(.*)$`・m/i) で読む (src/entry.ts の map 先勝ちパーサとは別コード)。
//      plugclass の slot 表も自前。type ∈ {1,2} と ps_files>=1 で判定。
//   5. `.fst` は tools/flp の parseFlp (読取専用の独立パーサ) で読み、**`.nfo` の
//      ps_file_filename_0 と 213 wrapper chunk の path が一致すること**を照合する
//      (実装側は spec.path と照合。この `.nfo` ↔ `.fst` の間接照合は検収側独自)。
//   6. SIGKILL 越えは自前の子プロセス (flush 0 のまま自殺) を spawn し、別 Wvfs で読み戻す。
//   7. レジストリ整合と陰性制御 (既定 dbPath は /c/home 外) も createMapper で再現。
//
// 数え方の定義 (規則 36):
//   entry    = 実ディスクの木で `Installed/(Effects|Generators)/**/*.nfo` にマッチするファイル数。
//   ファイル  = 木の下の**通常ファイル**数 (.nfo/.fst/.Plugins.ini/VerifiedIDs.nfo を含む)。
//   受理      = ps_files>=1 かつ全 i について plugclass が slot 表で有効 かつ type ∈ {1,2}。
//   ジャーナル = 本スクリプトでは数えない (h4_recount.mjs の担当)。
// 書込は tools/hostbridge/nfo/work 配下のみ。exit 0 = 全項目 PASS。
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { createMapper } from '../../shimx/pathreg/js/pathmap.mjs';
import { parseFlp, writeFlp, firstDiff } from '../../flp/src/flp.ts';
import { parseWrapperData } from '../../flp/src/summary.ts';
import { DEFAULT_DB_PATH } from './src/generate.ts';
import { createPathRouter } from '../../assets/wvfs/pathlink.ts';
import { Wvfs, NodeBackend, storeDir } from '../../assets/wvfs/index.ts';

const NFO = path.dirname(new URL(import.meta.url).pathname); // tools/hostbridge/nfo
const WORK = path.join(NFO, 'work', 'h4-accept');
const CLI_OUT = path.join(WORK, 'cli-out');
const STORE_MAIN = path.join(WORK, 'vfs-main');
const STORE_KILL = path.join(WORK, 'vfs-kill');
const HOME = '/c/home';
const sha = (b) => createHash('sha256').update(b).digest('hex');
const t0 = Date.now();
const t0Load = fs.readFileSync('/proc/loadavg', 'utf8').split(' ').slice(0, 3).join(' ');
let failed = 0;
const must = (cond, msg) => { console.log(cond ? '  ok  ' : '  FAIL', msg); if (!cond) failed++; };

const VREG_SEED = path.join(NFO, '..', '..', 'startup', 'data', 'vreg_seed.json');
const SPECS_JSON = path.join(NFO, 'specs', 'wasm_plugins.json');
const KH_INDEX = path.join(NFO, '..', '..', 'targets', 'kilohearts', 'work', 'macpkg', 'product_index.json');

// ---- 実ディスクの木を再帰 walk して通常ファイルの相対パス (posix) を集める ----
function walkDir(root) {
  const out = [];
  const rec = (rel) => {
    for (const d of fs.readdirSync(rel ? path.join(root, rel) : root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const r = rel ? rel + '/' + d.name : d.name;
      if (d.isDirectory()) rec(r); else out.push(r);
    }
  };
  rec('');
  return out;
}

// ================================================================ ② db root の導出 (vreg seed・検収側自前の文字列連結)
console.log('== ② db root 導出 (vreg seed から自前連結)');
const seed = JSON.parse(fs.readFileSync(VREG_SEED, 'utf8'));
const shared = seed.HKCU['Software\\Image-Line\\Shared\\Paths']['Shared data'].v;
const dbRootWin = shared.replace(/[\\/]+$/, '') + '\\FL Studio\\Presets\\Plugin database';
console.log(`   Shared data = ${shared}\n   dbRootWin   = ${dbRootWin}`);

// ================================================================ ① 生成 (CLI 別プロセス)
console.log('== ① generate via cli/gen.ts (別プロセス・実ディスク)');
fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(CLI_OUT, { recursive: true });
execFileSync(process.execPath, [path.join(NFO, 'cli', 'gen.ts'), SPECS_JSON, CLI_OUT, '--kilohearts', KH_INDEX], { stdio: 'inherit' });
const disk = walkDir(CLI_OUT).map((rel) => ({
  rel,
  win: `${dbRootWin}\\${rel.replace(/\//g, '\\')}`,
  bytes: fs.readFileSync(path.join(CLI_OUT, rel)),
}));
const entryRel = disk.filter((f) => /^Installed\/(Effects|Generators)\/.+\.nfo$/.test(f.rel));
console.log(`   walk: files=${disk.length} entry .nfo=${entryRel.length} bytes=${disk.reduce((n, f) => n + f.bytes.length, 0)}`);
must(disk.length === 102, `ファイル = 102 (実測 ${disk.length})`);
must(entryRel.length === 50, `entry = 50 (実測 ${entryRel.length})`);
must(disk.filter((f) => f.rel.endsWith('.fst')).length === 50, `.fst = 50 (実測 ${disk.filter((f) => f.rel.endsWith('.fst')).length})`);
must(disk.some((f) => f.rel === 'Installed/.Plugins.ini') && disk.some((f) => f.rel === 'Installed/VerifiedIDs.nfo'), 'Installed 直下に .Plugins.ini と VerifiedIDs.nfo');

// ================================================================ ②b 写 Mapping (pathreg JS ミラー・自前 strip)
console.log('== ②b 写 Mapping (pathreg JS ミラー createMapper)');
const mapper = createMapper();
const toVfs = (win) => {
  const raw = mapper.map(win);
  if (!raw) return null;
  if (raw !== HOME && !raw.startsWith(HOME + '/')) return null; // /c 直下・/fl (RO) は対象外
  return raw.slice(HOME.length) || '/';
};
const dbRootVfs = toVfs(dbRootWin);
console.log(`   dbRoot vfs = ${dbRootVfs}`);
must(dbRootVfs === '/Documents/Image-Line/FL Studio/Presets/Plugin database', `db root → ${dbRootVfs}`);
must(toVfs(shared) === '/Documents/Image-Line', `Shared data → ${toVfs(shared)}`);
// 既定 persona と vreg seed の一致
const userProfile = seed._env?.USERPROFILE ?? null;
const personal = seed._known_folders?.['CSIDL_PERSONAL(5)'] ?? null;
must((userProfile ?? '').toLowerCase() === 'c:\\users\\webstudio', `USERPROFILE = ${userProfile} (pathreg 既定と一致)`);
must((personal ?? '').toLowerCase() === 'c:\\users\\webstudio\\documents', `CSIDL_PERSONAL = ${personal}`);
// cross-module: pathlink (TS) の route と pathreg JS ミラーが同じ結論を出すこと
const pl = createPathRouter();
must(pl.route(dbRootWin)?.path === dbRootVfs, `pathlink.route と createMapper が一致 (${pl.route(dbRootWin)?.path})`);
must(pl.route(DEFAULT_DB_PATH) === null, `pathlink: DEFAULT_DB_PATH は route = null`);
must(toVfs(DEFAULT_DB_PATH) === null, `createMapper: DEFAULT_DB_PATH は ${mapper.map(DEFAULT_DB_PATH)} (HOME 外 → 書込対象外)`);

// ================================================================ ③ 仮想 FS 書込 (自前ループ)
console.log('== ③ write to wvfs (自前 mkdirp/writeFileSync ループ)');
const mainStoreDir = path.join(STORE_MAIN, storeDir('home', 'fl-h4-accept'));
const w = await Wvfs.open(new NodeBackend(mainStoreDir));
let routeFail = 0;
const manifest = [];
for (const f of disk) {
  const vp = toVfs(f.win);
  if (!vp) { routeFail++; continue; }
  w.mkdirpSync(vp.slice(0, vp.lastIndexOf('/')));
  w.writeFileSync(vp, f.bytes);
  manifest.push({ rel: f.rel, vpath: vp, size: f.bytes.length, sha: sha(f.bytes) });
}
must(routeFail === 0, `route 失敗 0 (実測 ${routeFail})`);
must(manifest.length === 102, `書込 102 (実測 ${manifest.length})`);
must(w.stats.files === 102, `wvfs index files 102 (実測 ${w.stats.files})`);
console.log(`   journal: ${JSON.stringify(w.debugState())}`);

// ================================================================ ④ 読み戻し (自前ループ)
console.log('== ④ read back from wvfs');
const back = new Map();
const bad = [];
let caseOk = 0;
for (const m of manifest) {
  let d;
  try { d = w.readFileSync(m.vpath); } catch (e) { bad.push(`${m.rel}: read failed`); continue; }
  if (d.length !== m.size) bad.push(`${m.rel}: size ${d.length}/${m.size}`);
  else if (sha(d) !== m.sha) bad.push(`${m.rel}: sha256 不一致`);
  else back.set(m.rel, d);
  const up = m.vpath.toUpperCase();
  if (up !== m.vpath) {
    try { if (sha(w.readFileSync(up)) === m.sha) caseOk++; else bad.push(`${m.rel}: 大文字読みで中身不一致`); }
    catch { bad.push(`${m.rel}: 大文字読み失敗`); }
  }
}
must(bad.length === 0, `読み戻し sha256 不一致 0 (実測 ${bad.length}${bad.length ? ': ' + bad[0] : ''})`);
must(back.size === 102, `読めた 102 (実測 ${back.size})`);
must(caseOk === 102, `大文字小文字変え読み一致 102/102 (実測 ${caseOk})`);
// 余剰ファイル: DB root 配下を自前 walk
const vfsFiles = [];
const vwalk = (p) => {
  for (const n of w.readdirSync(p).sort()) {
    const c = p === '/' ? `/${n}` : `${p}/${n}`;
    const st = w.statSync(c);
    if (st?.type === 'dir') vwalk(c); else vfsFiles.push(c);
  }
};
vwalk(dbRootVfs);
const expect = new Set(manifest.map((m) => m.vpath));
const extra = vfsFiles.filter((p) => !expect.has(p));
must(extra.length === 0, `余剰ファイル 0 (実測 ${extra.length})`);
must(vfsFiles.length === 102, `DB root 配下のファイル 102 (実測 ${vfsFiles.length})`);
must(w.readdirSync(dbRootVfs + '/Installed').sort().join(',') === '.Plugins.ini,Effects,Generators,VerifiedIDs.nfo',
  `Installed 直下 = ${w.readdirSync(dbRootVfs + '/Installed').sort().join(',')}`);

// ================================================================ ⑤ round-trip: .nfo 受理 (正規表現パーサ)
console.log('== ⑤ round-trip: .nfo 受理 (検収側の正規表現パーサ)');
const SLOT = [
  { cls: 2, gen: 3, s32: 0, s64: 1 }, { cls: 0, gen: 4, s32: 2, s64: 3 },
  { cls: 7, gen: 8, s32: 4, s64: 5 }, { cls: 9, gen: 10, s32: -1, s64: 6 }, { cls: 11, gen: 12, s32: -1, s64: 7 },
];
const slotOf = (pc, is64) => { for (const f of SLOT) { if (pc === f.cls || pc === f.gen) return is64 ? f.s64 : f.s32; } return -1; };
const keyAt = (text, key) => {
  const m = text.match(new RegExp('^' + key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=(.*)$', 'mi'));
  return m ? m[1].replace(/\r$/, '') : undefined;
};
const numAt = (text, key, def) => {
  const v = keyAt(text, key);
  if (v === undefined) return def;
  const t = v.trim();
  if (/^-?\d+$/.test(t)) return Number(t);
  return def;
};
let accepted = 0, dropped = 0, rejected = 0, dupKeys = 0, nameMismatch = 0;
const family = {};
for (const f of entryRel) {
  const text = new TextDecoder().decode(back.get(f.rel));
  // 重複キー検出 (先勝ち規則の別角度)
  for (const k of ['fileversion', 'ps_name', 'ps_files']) {
    const n = (text.match(new RegExp('^' + k + '=', 'gmi')) || []).length;
    if (n > 1) dupKeys++;
  }
  const n = numAt(text, 'ps_files', 0);
  let usable = 0;
  for (let i = 0; i < n; i++) {
    const pc = numAt(text, `ps_file_plugclass_${i}`, -1);
    if (pc < 0) { rejected++; continue; }
    if (slotOf(pc, numAt(text, `ps_file_bitsize_${i}`, 32) === 64) < 0) { rejected++; continue; }
    if (![1, 2].includes(numAt(text, `ps_file_type_${i}`, 0))) { rejected++; continue; }
    usable++;
  }
  if (usable > 0 && n >= 1) accepted++; else dropped++;
  const seg = f.rel.replace(/^Installed\//, '').split('/');
  const fam = `${seg[0]}/${seg[1]}`;
  family[fam] = (family[fam] ?? 0) + 1;
  // 生成時 spec 名 (ファイル名) と ps_name の対応をウォークから再構成
  const base = f.rel.split('/').pop().replace(/\.nfo$/, '');
  if (keyAt(text, 'ps_name') !== base) nameMismatch++;
}
must(accepted === 50 && dropped === 0, `nfo 受理 50/50・drop 0 (実測 ${accepted}/${dropped})`);
must(rejected === 0, `rejectedFiles 0 (実測 ${rejected})`);
must(dupKeys === 0, `重複キー 0 (実測 ${dupKeys})`);
must(nameMismatch === 0, `ps_name = ファイル名 (不一致 ${nameMismatch})`);
console.log(`   byFamily: ${JSON.stringify(family)}`);

// ================================================================ ⑥ round-trip: .fst (tools/flp 独立パーサ + .nfo 突合)
console.log('== ⑥ round-trip: .fst (parseFlp + .nfo の ps_file_filename_0 と 213 の照合)');
let fstParsed = 0, fstRt = 0, wrapperPath = 0, name203 = 0, ev = { 199: 0, 201: 0, 203: 0, 212: 0, 213: 0 };
const fstProblems = [];
for (const f of entryRel) {
  const nfoText = new TextDecoder().decode(back.get(f.rel));
  const fstRel = f.rel.replace(/\.nfo$/, '.fst');
  const b = back.get(fstRel);
  if (!b) { fstProblems.push(`${fstRel}: 無い`); continue; }
  const fl = parseFlp(b);
  fstParsed++;
  if (firstDiff(b, writeFlp(fl)) === -1) fstRt++; else fstProblems.push(`${fstRel}: parseFlp→writeFlp byte 不一致`);
  for (const e of fl.events) if (e.id in ev) ev[e.id]++;
  const e213 = fl.events.find((x) => x.id === 213);
  const wd = e213 ? parseWrapperData(e213.data) : null;
  if (wd && wd.path === keyAt(nfoText, 'ps_file_filename_0')) wrapperPath++;
  else fstProblems.push(`${fstRel}: 213 path=${wd?.path} != ps_file_filename_0=${keyAt(nfoText, 'ps_file_filename_0')}`);
  const e203 = fl.events.find((x) => x.id === 203);
  if (e203) { const nm = new TextDecoder('utf-16le').decode(e203.data).replace(/\0+$/, ''); if (nm === keyAt(nfoText, 'ps_name')) name203++; }
}
must(fstParsed === 50 && fstRt === 50, `.fst parseFlp ${fstParsed} / writeFlp byte-exact ${fstRt}`);
must(Object.values(ev).every((v) => v === 50), `event 199/201/203/212/213 が各 50 (実測 ${JSON.stringify(ev)})`);
must(wrapperPath === 50, `213 wrapper path = ps_file_filename_0 が 50 件一致 (実測 ${wrapperPath})`);
must(name203 === 50, `203 name = ps_name が 50 件一致 (実測 ${name203})`);
must(fstProblems.length === 0, `fst problems 0 (実測 ${fstProblems.length}${fstProblems.length ? ': ' + fstProblems[0] : ''})`);

// ================================================================ ⑦ .Plugins.ini / VerifiedIDs.nfo
console.log('== ⑦ .Plugins.ini / VerifiedIDs.nfo (自前パーサ)');
const iniText = new TextDecoder().decode(back.get('Installed/.Plugins.ini'));
const iniSecs = [];
for (const line of iniText.split(/\r\n|\n|\r/)) {
  if (line === '') continue;
  if (line.startsWith('[') && line.endsWith(']')) iniSecs.push({ name: line.slice(1, -1), lines: [] });
  else if (iniSecs.length) iniSecs[iniSecs.length - 1].lines.push(line);
}
must(iniSecs.length === 50, `ini セクション 50 (実測 ${iniSecs.length})`);
let iniVerbatim = 0;
for (const f of entryRel) {
  const want = f.rel.replace(/^Installed\//, '').replace(/\.nfo$/, '').replace(/\//g, '\\').toUpperCase();
  const sec = iniSecs.find((s) => s.name.toUpperCase() === want);
  const nfoLines = new TextDecoder().decode(back.get(f.rel)).split(/\r\n|\n|\r/).filter((l) => l !== '');
  if (sec && sec.lines.length === nfoLines.length && sec.lines.every((l, i) => l === nfoLines[i])) iniVerbatim++;
}
must(iniVerbatim === 50, `ini セクション本編 = .nfo 本編 verbatim 50 (実測 ${iniVerbatim})`);
const vidsText = new TextDecoder().decode(back.get('Installed/VerifiedIDs.nfo'));
const vidKeys = vidsText.split(/\r\n|\n|\r/).filter((l) => l !== '' && !l.startsWith("'"));
must(vidKeys.length === 50, `VerifiedIDs キー 50 (実測 ${vidKeys.length})`);
let vidsRef = 0;
for (const f of entryRel) {
  const rel = f.rel.slice('Installed/'.length).replace(/\.nfo$/, '.NFO').replace(/\//g, '\\');
  if (vidKeys.some((l) => { const p = l.indexOf('='); return p > 0 && l.slice(p + 1).toUpperCase() === rel.toUpperCase(); })) vidsRef++;
}
must(vidsRef === 50, `VerifiedIDs が全 entry .NFO を参照 50 (実測 ${vidsRef})`);

// ================================================================ ⑧ SIGKILL 越え (自前子プロセス・flush 0)
console.log('== ⑧ SIGKILL 越え (自前子プロセス・flush 0)');
const child = path.join(WORK, 'accept_kill_child.mjs');
fs.writeFileSync(child, `
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { Wvfs, NodeBackend, storeDir } from '../../../../assets/wvfs/index.ts';
const [storeBase, cliOut, dbRootWin] = [process.argv[2], process.argv[3], process.argv[4]];
const files = [];
const rec = (rel) => {
  for (const d of fs.readdirSync(rel ? path.join(cliOut, rel) : cliOut, { withFileTypes: true })) {
    const r = rel ? rel + '/' + d.name : d.name;
    if (d.isDirectory()) rec(r); else files.push(r);
  }
};
rec('');
const w = await Wvfs.open(new NodeBackend(path.join(storeBase, storeDir('home', 'fl-h4-accept'))), { flushOnClose: false });
for (const rel of files) {
  const bytes = fs.readFileSync(path.join(cliOut, rel));
  const raw = ('${HOME}' + '/Documents/Image-Line/FL Studio/Presets/Plugin database/' + rel).slice('${HOME}'.length);
  w.mkdirpSync(raw.slice(0, raw.lastIndexOf('/')));
  w.writeFileSync(raw, bytes);
}
console.log('[child] flushes=' + w.stats.flushes + ' files=' + w.stats.files + ' (close しない) -> SIGKILL');
process.kill(process.pid, 'SIGKILL');
`);
const cp = spawn(process.execPath, [child, STORE_KILL, CLI_OUT, dbRootWin], { stdio: 'inherit' });
const killRun = await new Promise((res) => cp.on('exit', (code, signal) => res({ code, signal })));
must(killRun.signal === 'SIGKILL', `子プロセスが SIGKILL で死んだ (signal=${killRun.signal}, code=${killRun.code})`);
const wk = await Wvfs.open(new NodeBackend(path.join(STORE_KILL, storeDir('home', 'fl-h4-accept'))));
must(wk.stats.files === 102, `SIGKILL 後に files 102 (実測 ${wk.stats.files})`);
must(wk.stats.flushes === 0, `子プロセスの flush 回数 0 (実測 ${wk.stats.flushes} を reload 後の stats で確認)`);
const killBad = [];
let killCase = 0;
for (const m of manifest) {
  try {
    const d = wk.readFileSync(m.vpath);
    if (sha(d) !== m.sha) killBad.push(`${m.rel}: sha256 不一致`);
  } catch { killBad.push(`${m.rel}: 読めない`); }
  try { if (sha(wk.readFileSync(m.vpath.toUpperCase())) === m.sha) killCase++; } catch { killBad.push(`${m.rel}: 大文字読み失敗`); }
}
must(killBad.length === 0, `SIGKILL/reload 後の sha256 不一致 0 (実測 ${killBad.length}${killBad.length ? ': ' + killBad[0] : ''})`);
must(killCase === 102, `SIGKILL/reload 後の大小変え読み 102/102 (実測 ${killCase})`);
await wk.close();

// ================================================================ ⑨ 陰性制御: 既定 dbPath では書込先が決まらない
console.log('== ⑨ 陰性制御: dbPath 未上書き (既定 DEFAULT_DB_PATH)');
must(toVfs(DEFAULT_DB_PATH) === null, `createMapper: DEFAULT_DB_PATH → ${mapper.map(DEFAULT_DB_PATH)} (HOME 外)`);
const wn = await Wvfs.open(new NodeBackend(path.join(WORK, 'vfs-neg', storeDir('home', 'fl-h4-accept'))));
let negFail = 0;
for (const f of disk) { if (!toVfs(`${DEFAULT_DB_PATH}\\${f.rel.replace(/\//g, '\\')}`)) negFail++; }
must(negFail === 102, `既定 dbPath では全ファイルの経路が決まらない (実測 ${negFail}/102)`);
must(wn.stats.files === 0, `書込 0 件 (実測 ${wn.stats.files})`);
await wn.close();
await w.close();

// ================================================================ ⑨b アブレーション: 1 バイト改変で round-trip 検査が落ちるか
console.log('== ⑨b アブレーション: .nfo を 1 バイト改変 → 受理/一致検査が FAIL すること');
{
  const orig = back.get('Installed/Effects/VST/OTT.nfo');
  const tampered = new Uint8Array(orig);
  const t0s = new TextDecoder().decode(tampered);
  const i = t0s.indexOf('ps_file_plugclass_0=0');
  tampered[i + 'ps_file_plugclass_0='.length] = 0x31; // '0' → '1' (class 1 = DX fx = slot 表に無し)
  const t = new TextDecoder().decode(tampered);
  const n = numAt(t, 'ps_files', 0);
  let usable = 0;
  for (let k = 0; k < n; k++) {
    const pc = numAt(t, `ps_file_plugclass_${k}`, -1);
    if (pc < 0) continue;
    if (slotOf(pc, numAt(t, `ps_file_bitsize_${k}`, 32) === 64) < 0) continue;
    if (![1, 2].includes(numAt(t, `ps_file_type_${k}`, 0))) continue;
    usable++;
  }
  must(usable === 0, `改変後は usable 0 → 受理 0 に落ちる (実測 usable=${usable})`);
  must(tampered.length === orig.length && t !== t0s, '改変は 1 バイト (長さ不変)');
  // 別の 1 バイト改変: ps_file_filename_0 の先頭を変えると 213 wrapper chunk の path と不一致になる
  const t2 = new Uint8Array(orig);
  const j = t0s.indexOf('ps_file_filename_0=') + 'ps_file_filename_0='.length;
  t2[j] = 0x5a; // 'C' → 'Z'
  const fl = parseFlp(back.get('Installed/Effects/VST/OTT.fst'));
  const e213 = fl.events.find((x) => x.id === 213);
  const wd = e213 ? parseWrapperData(e213.data) : null;
  must(wd?.path !== keyAt(new TextDecoder().decode(t2), 'ps_file_filename_0'), '改変後は 213 path と ps_file_filename_0 が不一致になる');
  must(t0s.includes('ps_file_plugclass_0=0'), '戻し後の原本は plugclass=0 を保持');
}

// ================================================================ 照合
const out = {
  files: disk.length, entries: entryRel.length, fst: 50, nfoAccepted: accepted, nfoDropped: dropped,
  rejectedFiles: rejected, fstParsed, fstRoundTrip: fstRt, wrapperPath, name203, iniSections: iniSecs.length,
  iniVerbatim, verifiedKeys: vidKeys.length, verifiedRefs: vidsRef,
  readBackMismatch: bad.length, caseVariant: caseOk, extraFiles: extra.length,
  killReload: { signal: killRun.signal, mismatches: killBad.length, caseVariant: killCase, flushes: wk.stats.flushes },
  negative: { defaultDbPathRoute: toVfs(DEFAULT_DB_PATH), unroutable: negFail, filesPlaced: 0 },
  family, dbRootVfs, sharedData: shared, dbRootWin,
};
console.log('\n' + JSON.stringify(out));
const t1 = Date.now();
console.log(`\nload average: start ${t0Load} / end ${fs.readFileSync('/proc/loadavg', 'utf8').split(' ').slice(0, 3).join(' ')} | elapsed ${((t1 - t0) / 1000).toFixed(2)} s`);
if (failed) { console.error(`\nFAIL ${failed}`); process.exit(1); }
console.log('\n全項目 PASS (検収側 独立再計算)');
