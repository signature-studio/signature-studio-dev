// カテゴリ別の圧縮率/速度ベンチ (win 資産ツリーのサンプル)。
//   node inventory/compress_bench.mjs [--budget-mb=48] [--chunk=1048576]
// 出力: inventory/compress_bench.json  (+ stdout の表)
// 注: zlib.* は libuv threadpool で並列実行 (UV_THREADPOOL_SIZE=16 を設定)。時間は wall ではなく CPU 時間の合算ではない点に注意。
process.env.UV_THREADPOOL_SIZE ??= '16';
import fs from 'node:fs';
import zlib from 'node:zlib';
import { promisify } from 'node:util';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const work = path.join(here, '..', 'work');
const args = Object.fromEntries(process.argv.slice(2).map((a) => a.replace(/^--/, '').split('=')));
const budget = Number(args['budget-mb'] ?? 48) * 1048576;
const CHUNK = Number(args.chunk ?? 1048576);

const c = zlib.constants;
const br = promisify(zlib.brotliCompress);
const zs = promisify(zlib.zstdCompress);
const gz = promisify(zlib.gzip);
const codecs = {
  'gzip-9': (b) => gz(b, { level: 9 }),
  'br-5': (b) => br(b, { params: { [c.BROTLI_PARAM_QUALITY]: 5, [c.BROTLI_PARAM_LGWIN]: 22, [c.BROTLI_PARAM_SIZE_HINT]: b.length } }),
  'br-9': (b) => br(b, { params: { [c.BROTLI_PARAM_QUALITY]: 9, [c.BROTLI_PARAM_LGWIN]: 22, [c.BROTLI_PARAM_SIZE_HINT]: b.length } }),
  'br-11': (b) => br(b, { params: { [c.BROTLI_PARAM_QUALITY]: 11, [c.BROTLI_PARAM_LGWIN]: 24, [c.BROTLI_PARAM_SIZE_HINT]: b.length } }),
  'zstd-3': (b) => zs(b, { params: { [c.ZSTD_c_compressionLevel]: 3 } }),
  'zstd-19': (b) => zs(b, { params: { [c.ZSTD_c_compressionLevel]: 19 } }),
};
const slowCodecs = new Set(['br-11', 'zstd-19']);

const inv = fs.readFileSync(path.join(work, 'inv_win.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
// 物理ブロック単位の unique
const seen = new Set();
const uniq = [];
for (const e of inv) {
  if (seen.has(e.disk)) continue;
  seen.add(e.disk);
  uniq.push(e);
}
const ext = (p) => (p.includes('.') ? p.split('.').pop().toLowerCase() : '');
const groupOf = (e) => {
  if (e.cat === 'exec') return `exec/${e.cls}`;
  if (e.cat === 'audio' || e.cat === 'preset' || e.cat === 'image' || e.cat === 'text') return `${e.cat}/${ext(e.p)}`;
  return e.cat;
};
const groups = new Map();
for (const e of uniq) {
  const g = groupOf(e);
  if (!groups.has(g)) groups.set(g, []);
  groups.get(g).push(e);
}
// 大きい群のみ個別行、小さい群は cat にまとめる
const bytesOf = (l) => l.reduce((a, e) => a + e.size, 0);
const rows = [...groups.entries()].filter(([, l]) => bytesOf(l) >= 3e6).sort((a, b) => bytesOf(b[1]) - bytesOf(a[1]));

function sample(list, limit) {
  const l = [...list].sort((a, b) => (a.sha < b.sha ? -1 : 1));
  const total = bytesOf(l);
  if (total <= limit) return l;
  // sha 順 (=擬似ランダム) に一定間隔で間引く
  const res = [];
  let b = 0;
  const stride = Math.max(1, Math.floor(l.length / Math.max(1, Math.round(l.length * limit / total))));
  for (let i = 0; i < l.length && b < limit; i += stride) {
    res.push(l[i]);
    b += l[i].size;
  }
  return res;
}

async function compressFileChunks(buf, fn, chunk) {
  let out = 0;
  const jobs = [];
  for (let o = 0; o < buf.length; o += chunk) jobs.push(fn(buf.subarray(o, Math.min(buf.length, o + chunk))));
  for (const r of await Promise.all(jobs)) out += r.length;
  return out;
}

const result = {};
const lines = [];
for (const [g, list] of rows) {
  const s = sample(list, slowCodecsBudget(g));
  const sz = bytesOf(s);
  const res = { sample_files: s.length, sample_bytes: sz, group_files: list.length, group_bytes: bytesOf(list), whole: {}, chunked: {} };
  const bufs = s.map((e) => fs.readFileSync(e.disk));
  for (const [name, fn] of Object.entries(codecs)) {
    // 遅いコーデックは予算を絞る
    let use = bufs;
    let useSz = sz;
    if (slowCodecs.has(name) && sz > 12e6) {
      use = [];
      useSz = 0;
      for (const b of bufs) {
        if (useSz > 12e6) break;
        use.push(b);
        useSz += b.length;
      }
    }
    if (name === 'br-11' && g.startsWith('exec')) {
      use = use.slice(0, 2);
      useSz = use.reduce((a, b) => a + b.length, 0);
    }
    let t = process.hrtime.bigint();
    const outs = await Promise.all(use.map((b) => fn(b)));
    let ms = Number(process.hrtime.bigint() - t) / 1e6;
    res.whole[name] = { in: useSz, out: outs.reduce((a, b) => a + b.length, 0), wall_ms: Math.round(ms) };
    // チャンク(CHUNK)独立圧縮
    t = process.hrtime.bigint();
    const cs = await Promise.all(use.map((b) => compressFileChunks(b, fn, CHUNK)));
    ms = Number(process.hrtime.bigint() - t) / 1e6;
    res.chunked[name] = { in: useSz, out: cs.reduce((a, b) => a + b, 0), wall_ms: Math.round(ms) };
  }
  result[g] = res;
  const f = (o) => (o.out / o.in).toFixed(3);
  lines.push(
    `${g.padEnd(18)} ${String(list.length).padStart(5)}f ${(bytesOf(list) / 1e6).toFixed(1).padStart(7)}MB | whole gz9 ${f(res.whole['gzip-9'])} br5 ${f(res.whole['br-5'])} br9 ${f(res.whole['br-9'])} br11 ${f(res.whole['br-11'])} z3 ${f(res.whole['zstd-3'])} z19 ${f(res.whole['zstd-19'])} | ${CHUNK >> 10}K-chunk br9 ${f(res.chunked['br-9'])} z19 ${f(res.chunked['zstd-19'])}`
  );
  console.log(lines[lines.length - 1]);
}
function slowCodecsBudget(g) {
  return g.startsWith('audio') ? Math.min(budget, 24e6) : budget;
}
fs.writeFileSync(path.join(here, 'compress_bench.json'), JSON.stringify({ chunk: CHUNK, budget_mb: budget / 1048576, result }, null, 1));
