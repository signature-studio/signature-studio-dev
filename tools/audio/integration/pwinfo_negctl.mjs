#!/usr/bin/env node
// ネガティブコントロール: e2e.mjs の pwInfo を抜き出し、write 窓の 4 通り (窓より前 / 窓の内側 / 窓の外側 / writes 空) を流して出力を見る。
//   node tools/audio/integration/pwinfo_negctl.mjs
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "e2e.mjs"), "utf8");
const m = /^const pwInfo = [\s\S]*?^};$/m.exec(src);
if (!m) throw new Error("pwInfo が e2e.mjs から抜き出せない");
const pwInfo = new Function(`return ${m[0].replace(/^const pwInfo = /, "")}`)();

const W = 256; // 1 write の frame 数 (B)
const PW_N = 1024; // flaudio.h の FLA_PW_N と一致させる
// 通算 n 件のうち直近 PW_N 件の write (k 番目 = w k*256, 起床・完了は 10 ms 間隔)
const mk = (n) => Array.from({ length: Math.min(n, PW_N) }, (_, j) => {
  const k = n - Math.min(n, PW_N) + j;
  return { w: k * W, fill: 256, wake_us: k * 10000, done_us: k * 10000 + 30 };
});
const cases = [
  ["窓より前 (失敗 56576、窓先頭 w=121856)", 1500, 56576],
  ["窓の内側 (失敗 256100、k=1000 の write の直後)", 1500, 256100],
  ["窓の外側 (失敗 384050、最新 write w=383744 より後)", 1500, 384050],
  ["writes 空 (pw_n=0)", 0, 56576],
];
for (const [name, n, under] of cases) {
  const v = { producer: { pw_n: n, writes: mk(n) }, underrun_count: 1, first_underrun_frame: under };
  console.log(`${name}\n  ${pwInfo(v)}`);
}
