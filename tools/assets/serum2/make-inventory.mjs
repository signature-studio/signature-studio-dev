// Serum 2 インストーラ展開物 (7z x) -> pack/pack.ts 入力 (inv.jsonl + tiers.json)
//   node make-inventory.mjs <extracted-root> <out-dir>
// 対象は content ディレクトリのみ ($COMMONFILES64 / $PLUGINSDIR = プラグイン本体・NSIS 部品は除外)。
// 期待値 (tools/targets/serum2/REPORT.md §1.1 / issue #70) と不一致なら exit 2。
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const [root, out] = process.argv.slice(2);
if (!root || !out) {
  console.error('usage: make-inventory.mjs <extracted-root> <out-dir>');
  process.exit(64);
}
export const EXPECT = {
  Multisamples: [4118, 939260634],
  Tables: [289, 173372140],
  Samples: [856, 203826813],
  Impulses: [110, 54516381],
  Skins: [691, 17356117],
  Presets: [627, 3909388],
  Other: [666, 583944],
};
const MAIN = new Set(['Multisamples', 'Tables', 'Samples', 'Impulses', 'Skins', 'Presets']);
const SKIP_TOP = new Set(['$COMMONFILES64', '$PLUGINSDIR']);
// 起動直後に要る (Skins/Presets/小物) = T1、Tables = T1 (音色選択で即必要)、Samples/Impulses = T2、Multisamples = T2 (オンデマンド)
const tierOf = (top) => (top === 'Multisamples' || top === 'Samples' || top === 'Impulses' ? 'T2' : 'T1');

const files = [];
(function walk(d, rel) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const r = rel ? rel + '/' + e.name : e.name;
    if (!rel && SKIP_TOP.has(e.name)) continue;
    if (e.isDirectory()) walk(path.join(d, e.name), r);
    else if (e.isFile()) files.push(r);
    else throw new Error('non-regular file: ' + r);
  }
})(root, '');
files.sort();

fs.mkdirSync(out, { recursive: true });
const inv = [];
const tiers = {};
const agg = {};
for (const p of files) {
  const disk = path.join(root, p);
  const buf = fs.readFileSync(disk);
  const top = p.split('/')[0];
  const grp = MAIN.has(top) ? top : 'Other';
  agg[grp] ??= [0, 0];
  agg[grp][0]++;
  agg[grp][1] += buf.length;
  const sha = crypto.createHash('sha256').update(buf).digest('hex');
  inv.push({ p, size: buf.length, disk, sha, cat: 'data', cls: 'data' });
  tiers[p] = tierOf(top);
}
fs.writeFileSync(path.join(out, 'inv.jsonl'), inv.map((x) => JSON.stringify(x)).join('\n') + '\n');
fs.writeFileSync(path.join(out, 'tiers.json'), JSON.stringify(tiers));
fs.writeFileSync(path.join(out, 'inventory-summary.json'), JSON.stringify(agg, null, 1));

let bad = 0;
let tf = 0;
let tb = 0;
for (const [k, [n, b]] of Object.entries(EXPECT)) {
  const got = agg[k] ?? [0, 0];
  const ok = got[0] === n && got[1] === b;
  if (!ok) bad++;
  tf += got[0];
  tb += got[1];
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${k.padEnd(13)} files ${got[0]} (期待 ${n})  bytes ${got[1]} (期待 ${b})`);
}
console.log(`total content files ${tf} bytes ${tb}`);
if (bad) {
  console.error(`inventory mismatch: ${bad} group(s)`);
  process.exit(2);
}
