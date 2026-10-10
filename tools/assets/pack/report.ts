// パッケージ実測レポート: 配置 dir / 拡張子 / tier 別の 非圧縮・格納サイズ (pack chunk は按分)。
//   node pack/report.ts work/pkg-full > PACKAGE_STATS.md
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { ManifestIndex } from '../vfs/manifest.ts';
import type { Manifest } from '../vfs/types.ts';

const dir = path.resolve(process.argv[2] ?? 'work/pkg-full');
const latest = JSON.parse(fs.readFileSync(path.join(dir, 'latest.json'), 'utf8'));
const m: Manifest = JSON.parse(zlib.brotliDecompressSync(fs.readFileSync(path.join(dir, latest.manifest))).toString());
const idx = new ManifestIndex(m);

type Acc = { files: number; raw: number; stored: number };
const byDir = new Map<string, Acc>();
const byExt = new Map<string, Acc>();
const add = (mp: Map<string, Acc>, k: string, raw: number, stored: number) => {
  const a = mp.get(k) ?? { files: 0, raw: 0, stored: 0 };
  a.files++;
  a.raw += raw;
  a.stored += stored;
  mp.set(k, a);
};
let stubs = 0;
let stubBytes = 0;
const seenContent = new Set<string>();
for (const [p, ref] of idx.walkFiles('')) {
  if (ref.stub) {
    stubs++;
    stubBytes += ref.size;
    continue;
  }
  if (ref.size === 0) continue;
  // 同一内容の別配置は 1 回だけ数える
  const key = `${ref.first}:${ref.off}`;
  if (seenContent.has(key)) continue;
  seenContent.add(key);
  let stored = 0;
  if (ref.off >= 0) stored = (ref.size / idx.chunkUsize(ref.first)) * idx.chunkCsize(ref.first);
  else for (const c of idx.fileChunks(ref)) stored += idx.chunkCsize(c);
  const parts = p.split('/');
  const top = parts[0] === 'Data' || parts[0] === 'Plugins' ? parts.slice(0, Math.min(3, parts.length - 1)).join('/') : parts.length > 1 ? parts[0] : '(root)';
  add(byDir, top, ref.size, stored);
  const e = parts[parts.length - 1].includes('.') ? parts[parts.length - 1].split('.').pop()!.toLowerCase() : '(none)';
  add(byExt, e, ref.size, stored);
}
const mb = (n: number) => (n / 1e6).toFixed(1);
const table = (title: string, mp: Map<string, Acc>, n: number) => {
  console.log(`\n### ${title}\n\n| key | files | 非圧縮 MB | 格納 MB | 格納/非圧縮 |\n|---|---:|---:|---:|---:|`);
  for (const [k, a] of [...mp].sort((x, y) => y[1].raw - x[1].raw).slice(0, n)) console.log(`| ${k} | ${a.files} | ${mb(a.raw)} | ${mb(a.stored)} | ${(a.stored / a.raw).toFixed(3)} |`);
};
const tot = [...byDir.values()].reduce((a, x) => ({ files: a.files + x.files, raw: a.raw + x.raw, stored: a.stored + x.stored }), { files: 0, raw: 0, stored: 0 });
console.log(`# PACKAGE_STATS (${m.name})\n`);
console.log(`- 配信対象 unique 内容: ${tot.files} 個 / 非圧縮 ${mb(tot.raw)} MB → 格納 ${mb(tot.stored)} MB (${(tot.stored / tot.raw).toFixed(3)})`);
console.log(`- stub (本体非配信): ${stubs} 個 / ${mb(stubBytes)} MB (元バイナリ。wasm 化/再ビルド後に別経路で配信)`);
console.log(`- chunk: ${m.chunks.n} 個 (chunkSize ${m.chunkSize}, pack ≤ ${m.smallMax}B 小ファイル同居)  manifest: ${latest.usize} B → br ${latest.size} B`);
console.log('\n### tier (配信 chunk 群)\n\n| tier | chunks | 非圧縮 MB | 格納 MB |\n|---|---:|---:|---:|');
for (const [g, rs] of Object.entries(m.groups)) {
  let u = 0;
  let c = 0;
  let n = 0;
  for (const [s, k] of rs) for (let i = s; i < s + k; i++, n++) {
    u += idx.chunkUsize(i);
    c += idx.chunkCsize(i);
  }
  console.log(`| ${g} | ${n} | ${mb(u)} | ${mb(c)} |`);
}
table('配置 dir 別', byDir, 24);
table('拡張子別', byExt, 24);
