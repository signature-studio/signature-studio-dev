#!/usr/bin/env node
// ネガティブコントロール: audio_app.ts の matchUnderrunWrite を抜き出し、合成 write 列で正例・負例・折り返しを流す。
// 判定が逆転しないこと (重なり有 → overlaps=true・gap=0 / 区間より前 → gap<0 / 区間より後 → gap>0) を確かめる。
//   node tools/audio/integration/uo_negctl.mjs    終了コード 0 = 全 PASS
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "../../../src/runtime/audio_app.ts"), "utf8");
const m = /export function matchUnderrunWrite\([^)]*\)[^{]*\{[\s\S]*?\n\}/.exec(src);
if (!m) throw new Error("matchUnderrunWrite が audio_app.ts から抜き出せない");
const fn = new Function(`return ${m[0]
  .replace(/^export function/, "function")
  .replace(/\(underrunUs: number, writes: \{[^)]*\}\[\]\)/, "(underrunUs, writes)")
  .replace(/: UnderrunWriteOverlap \| null/, "")
  .replace(/let best: UnderrunWriteOverlap \| null/, "let best")
  .replace(/const toWake = /g, "const toWake = ")}`)();

let fail = 0;
const check = (name, ok, detail) => { if (!ok) fail++; console.log(`${ok ? "PASS" : "FAIL"} ${name}: ${detail}`); };
const W = (w, wake, done) => ({ w, fill: 0, wake_us: wake >>> 0, done_us: done >>> 0 });
const writes = [W(0, 1_000_000, 1_000_400), W(256, 1_010_000, 1_010_300), W(512, 1_020_000, 1_020_500)];

// 正例: underrun が write 区間の内側
let r = fn(1_010_100, writes);
check("pos-inside", r.overlaps === true && r.gap_us === 0 && r.w === 256, JSON.stringify(r));
// 正例: 区間の端 (wake 丁度・done 丁度)
r = fn(1_010_000, writes);
check("pos-edge-wake", r.overlaps === true && r.gap_us === 0, JSON.stringify(r));
r = fn(1_010_300, writes);
check("pos-edge-done", r.overlaps === true && r.gap_us === 0, JSON.stringify(r));
// 負例: underrun が全 write より前 (最近傍の区間との差は負)
r = fn(999_000, writes);
check("neg-before", r.overlaps === false && r.gap_us === -1000 && r.w === 0, JSON.stringify(r));
// 負例: underrun が区間の後・次の wake より前 (最近傍は直前の done)
r = fn(1_005_000, writes);
check("neg-between-after-prev", r.overlaps === false && r.gap_us === 4600 && r.w === 0, JSON.stringify(r));
// 負例: underrun が最後の区間より後
r = fn(1_030_000, writes);
check("neg-after", r.overlaps === false && r.gap_us === 9500 && r.w === 512, JSON.stringify(r));
// 折り返し: u32 が 0xFFFFFFF0 付近から 0x10 へ回る区間の内側
const wrap = [W(0, 0xFFFFFF00, 0xFFFFFFF0), W(256, 0x00000000, 0x00000100)];
r = fn(0x00000050, wrap);
check("wrap-inside", r.overlaps === true && r.gap_us === 0 && r.w === 256, JSON.stringify(r));
r = fn(0xFFFFFF80, wrap);
check("wrap-inside-prev", r.overlaps === true && r.gap_us === 0 && r.w === 0, JSON.stringify(r));
// 空 write 列
r = fn(1, []);
check("empty", r === null, String(r));

console.log(fail ? `FAIL ${fail} 件` : "ALL PASS");
process.exit(fail ? 1 : 0);
