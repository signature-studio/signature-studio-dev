// 検出下限の実測: 実 FL 抽出物から n 個のランダム slice (size B) を切り出し、各々が deny-list に検出される率を出す。
//   node tools/legal/release-guard/measure.mjs <fl dir> [--denylist dir] [--n 60] [--seed 1]
// 検算 (別アルゴリズム): 切り出し元ファイルに対し Buffer.indexOf で slice が逐語に存在することを確認 (= 検出されるべき対象であること)。
import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import path from "node:path";
import { collectEntries, DEFAULT_DENYLIST, loadDenylist, WindowSampler } from "./lib.mjs";

const a = process.argv.slice(2);
const opt = (n, d) => (a.includes(`--${n}`) ? a[a.indexOf(`--${n}`) + 1] : d);
const dir = a.find((x) => !x.startsWith("--") && a[a.indexOf(x) - 1]?.startsWith("--") === false) ?? a[0];
const N = Number(opt("n", 60));
const dl = loadDenylist(path.resolve(opt("denylist", DEFAULT_DENYLIST)));
const has = (x) => { let lo = 0, hi = dl.windowsArr.length - 1; while (lo <= hi) { const m = (lo + hi) >>> 1, v = dl.windowsArr[m]; if (v === x) return true; if (v < x) lo = m + 1; else hi = m - 1; } return false; };
let s = Number(opt("seed", 1)) >>> 0;
const rnd = () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 2 ** 32;
const files = collectEntries({ src: [dir] }).filter((f) => statSync(f.file).size >= 1 << 20);
const rows = [];
for (const size of [512, 1024, 2048, 4096, 8192, 16384, 65536]) {
  let det = 0, verified = 0, samplerWins = 0;
  for (let i = 0; i < N; i++) {
    const f = files[Math.floor(rnd() * files.length)];
    const buf = readFileSync(f.file);
    const off = Math.floor(rnd() * (buf.length - size));
    const slice = buf.subarray(off, off + size);
    if (buf.indexOf(slice) >= 0) verified++;
    let hit = 0;
    new WindowSampler(dl.params, (fp) => { if (has(fp)) hit++; }).feed(slice);
    if (hit) det++;
  }
  rows.push({ sliceBytes: size, n: N, detected: det, rate: +(det / N).toFixed(3), verbatimInSource: verified });
}
console.log(JSON.stringify({ params: dl.params, denylist: dl.id, rows }, null, 1));
