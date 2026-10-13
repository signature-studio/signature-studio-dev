// 出力署名 (steady の sig) の整合検査。同じ (N, 軽量/標準) の中で chain を組む構成 (nocopy / jsdrive 以外) は全て同一署名でなければならない。
//   node check.mjs            results/p8.jsonl を検査 (不一致があれば exit 1)
//   node check.mjs --negative  1 件の署名を壊して FAIL (exit 1) することの確認 (期待: FAIL を検出 = exit 0)
import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const rows = fs.readFileSync(path.join(HERE, 'results/p8.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l)).filter((r) => r.mode === 'steady' && r.sig);
const neg = process.argv.includes('--negative');
if (neg) rows[Math.floor(rows.length / 2)] = { ...rows[Math.floor(rows.length / 2)], sig: 'deadbeef' };
const groups = new Map();
for (const r of rows) { if (/nocopy|jsdrive/.test(r.cfg)) continue; const k = `${r.runtime.split(' ')[0]} N=${r.N} ${r.cfg.endsWith('_light') ? 'light' : 'heavy'}`; (groups.get(k) ?? groups.set(k, new Map()).get(k)).set(r.cfg, (groups.get(k).get(r.cfg) ?? new Set()).add(r.sig)); }
let fail = 0, pass = 0;
for (const [k, m] of groups) {
  const all = new Set([...m.values()].flatMap((s) => [...s]));
  // 静的版は plugin ごとに PID 定数が違う (1e-30 級で出力に出ない) ため N≥2 でも署名一致を期待する
  if (all.size === 1) pass++; else { fail++; console.log(`FAIL ${k}: ${JSON.stringify([...m].map(([c, s]) => [c, [...s]]))}`); }
}
console.log(`${fail ? 'FAIL' : 'PASS'} signature groups: pass=${pass} fail=${fail} (rows=${rows.length})${neg ? ' [negative control]' : ''}`);
process.exit(neg ? (fail > 0 ? 0 : 1) : (fail ? 1 : 0));
