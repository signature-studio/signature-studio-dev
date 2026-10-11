// h4_accept_chrome.mjs — CAB-216 検収: Chrome/OPFS (実ディスクプロファイル) の永続を独立照合する。
//   node h4_accept_chrome.mjs <chrome-profile-dir> [cli-out-dir]
//
// 実装側 (h4/seed_worker.ts の verify フェーズ) とは別アルゴリズム:
//   - OPFS は Chrome プロファイル配下の LevelDB (Default/File System/000/t/00/NNNNNNNN) として
//     実ディスクに載っている。ここから**ジャーナル実ファイル**を直接読み、自前のレコードデコーダで
//     ツリーを復元する (wvfs の Journal/Wvfs クラスは import しない)。
//   - 照合相手は `cli/gen.ts` が実ディスクに書いた木 (work/h4-accept/cli-out)。生成器は同一でも
//     経路が全く違う (browser worker 経由 vs node CLI。OPFS backend 経由 vs fs.writeFileSync)。
//   - sha256 は node:crypto で別計算。
//
// 数え方の定義 (規則 36):
//   ファイル = DB root (`/Documents/Image-Line/FL Studio/Presets/Plugin database/`) 配下の実ファイル数。
//   一致     = 同 rel パスの CLI 生成ファイルと **sha256 が一致**した件数。
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

const prof = process.argv[2];
if (!prof) {
  console.error(`usage: node h4_accept_chrome.mjs <chrome-profile-dir> [cli-out-dir]
  先に node h4_accept_check.mjs を実行し、work/h4/chrome-profiles/h4-e2e-* と
  work/h4-accept/cli-out を生成しておくこと。`);
  process.exit(2);
}
const cliOut = process.argv[3] ?? path.join(path.dirname(new URL(import.meta.url).pathname), 'work', 'h4-accept', 'cli-out');
if (!fs.existsSync(cliOut)) {
  console.error(`CLI 生成木が無い: ${cliOut}\n先に node h4_accept_check.mjs を実行せよ。`);
  process.exit(2);
}
const JHDR = 4096;
const REC_HEAD = 27; // recLen(4) crc(4) seq(4) op(1) pathLen(2) dataLen(4) mtime(8)
const DB_PREFIX = '/Documents/Image-Line/FL Studio/Presets/Plugin database/';
const results = {};
let failed = 0;
const must = (c, m) => { console.log(c ? '  ok  ' : '  FAIL', m); if (!c) failed++; };
const sha = (b) => createHash('sha256').update(b).digest('hex');

// LevelDB 管理ファイルからジャーナルらしいものを探す (magic 'WVJ1' / サイズ >= JHDR)
const dirs = [path.join(prof, 'Default', 'File System')];
const jo = [];
const scan = (d) => {
  if (!fs.existsSync(d)) return;
  for (const n of fs.readdirSync(d, { withFileTypes: true }).map((x) => x.name).sort()) {
    const p = path.join(d, n);
    const st = fs.statSync(p);
    if (st.isDirectory()) { scan(p); continue; }
    if (st.size < JHDR) continue;
    const fd = fs.openSync(p, 'r');
    const head = Buffer.alloc(4);
    fs.readSync(fd, head, 0, 4, 0);
    fs.closeSync(fd);
    if (head.toString('latin1') === 'WVJ1') jo.push({ p, size: st.size });
  }
};
for (const d of dirs) scan(d);
console.log(`== OPFS journal candidates (magic WVJ1): ${jo.length}`);
for (const j of jo) console.log(`   ${path.relative(prof, j.p)}  ${j.size} B`);

// 各ジャーナルを自前デコードして DB ツリーを復元
const dec = {
  root: (b) => {
    // スーパーブロック (root) から active journalId を取る
    const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    const SLOT = 2048;
    let best = -1, id = 1;
    for (const s of [0, 1]) {
      if (b.length < (s + 1) * SLOT) break;
      if (b[s * SLOT] !== 0x57 || b[s * SLOT + 1] !== 0x56 || b[s * SLOT + 2] !== 0x53 || b[s * SLOT + 3] !== 0x31) continue;
      if (dv.getUint32(s * SLOT + 4, true) !== 1) continue;
      const g = dv.getUint32(s * SLOT + 8, true);
      if (g > best) { best = g; id = dv.getUint32(s * SLOT + 12, true); }
    }
    return id;
  },
  body: (b) => {
    const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    const files = new Map();
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
      else if (op === 3) mkdirs++;
      else if (op === 2) { dels++; files.delete(p); }
      q += recLen;
    }
    return { files, stats: { recs, puts, mkdirs, dels, torn } };
  },
};

// CLI 生成木を基準に読む (rel → sha256)
const cli = new Map();
const rec2 = (rel) => {
  for (const d of fs.readdirSync(rel ? path.join(cliOut, rel) : cliOut, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const r = rel ? rel + '/' + d.name : d.name;
    if (d.isDirectory()) rec2(r); else cli.set(r, sha(fs.readFileSync(path.join(cliOut, r))));
  }
};
if (!fs.existsSync(cliOut)) {
  console.error(`CLI 生成木が無い: ${cliOut}\n先に node h4_accept_check.mjs を実行せよ (work/h4-accept/cli-out を生成する)。`);
  process.exit(2);
}
if (fs.existsSync(cliOut)) rec2('');
console.log(`== CLI 生成木: files=${cli.size}`);

let checkedStores = 0;
for (const j of jo) {
  const b = new Uint8Array(fs.readFileSync(j.p));
  let tree;
  try { tree = dec.body(b); } catch (e) { console.log(`   ${path.basename(j.p)}: デコード失敗 ${e}`); continue; }
  const db = [...tree.files.entries()].filter(([p]) => p.startsWith(DB_PREFIX) && p.length > DB_PREFIX.length);
  if (db.length === 0) {
    // DB を含まない store (陰性制御 3 の probe store)。DB 件数での検査対象外とするが、
    // no-flush 書込が SIGKILL 越えで残ったかは別途上で記録する。
    const probe = [...tree.files.entries()].find(([p, d]) => new TextDecoder().decode(d).includes('H4-NOFLUSH-PROBE'));
    console.log(`   ${path.basename(j.p)}: DB ファイル 0 → DB 件数検査の対象外${probe ? ' (no-flush probe 有)' : ''}`);
    continue;
  }
  checkedStores++;
  console.log(`== store ${path.relative(prof, j.p)}: DB files=${db.length} journal=${JSON.stringify(tree.stats)}`);
  must(tree.stats.torn === 0, `torn tail 0 (実測 ${tree.stats.torn})`);
  const missing = [];
  const mism = [];
  let ok = 0;
  for (const [p, data] of db) {
    const rel = p.slice(DB_PREFIX.length);
    const want = cli.get(rel);
    if (want === undefined) { missing.push(rel); continue; }
    if (sha(data) === want) ok++; else mism.push(rel);
  }
  const notInStore = [...cli.keys()].filter((r) => !db.some(([p]) => p === DB_PREFIX + r));
  must(missing.length === 0, `OPFS にあって CLI に無いファイル 0 (実測 ${missing.length})`);
  must(notInStore.length === 0, `CLI にあって OPFS に無いファイル 0 (実測 ${notInStore.length})`);
  must(mism.length === 0, `sha256 不一致 0 (実測 ${mism.length}${mism.length ? ': ' + mism.slice(0, 3).join(', ') : ''})`);
  must(ok === cli.size, `OPFS 実物と CLI 生成物の sha256 一致 ${ok}/${cli.size}`);
  const extra = [...tree.files.entries()].filter(([p]) => !p.startsWith(DB_PREFIX) && !p.startsWith('/'));
  if (extra.length) {
    // 陰性制御 3 の実測痕跡: flush 点を飛ばして書かれた内容が SIGKILL 後の実ディスクに残っているか
    const probe = extra.find(([p, d]) => new TextDecoder().decode(d).includes('H4-NOFLUSH-PROBE'));
    const detail = extra.map(([p, d]) => `${p} (${d.length} B)`).slice(0, 5);
    console.log(`   非 DB エントリ (${extra.length}): ${detail.join(', ')}`);
    console.log(`   陰性制御 3 実測: flush 点無しの書込が SIGKILL 後も実ディスクに ${probe ? '残った (H4-NOFLUSH-PROBE 有)' : '残っていない'}`);
    if (probe) results.noflushSurvived = true;
  }
  const lower = new Map();
  for (const p of tree.files.keys()) { const l = p.toLowerCase(); lower.set(l, (lower.get(l) ?? 0) + 1); }
  const dup = [...lower.values()].filter((n) => n > 1).length;
  must(dup === 0, `store 内に大文字小文字のみで衝突するパス 0 (実測 ${dup})`);
}

if (checkedStores === 0) { console.error('OPFS に DB を含むジャーナルが見つからなかった'); process.exit(2); }
if (failed) { console.error(`\nFAIL ${failed}`); process.exit(1); }
console.log('\n全項目 PASS (検収側 Chrome/OPFS 独立照合)');
