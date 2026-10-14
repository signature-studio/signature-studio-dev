// AU-2 (#187) 行列の集計: results/au2/<cond>_r<rep>.json を読み、セルごとの P1〜P4 を Markdown 表で出す。
// 使い方: node tools/audio/au2_summary.mjs [results/au2 のパス]
// P2 は worklet が公開する burst_obs (連続 process の総フレーム数の最大値) のみ。p99 は未計測 (分布を取るには worklet 側の拡張が要る)。
// P4: T_req = ceil((burst×1.25 + B)/B)×B を各セルの最大 burst から再計算し、実 T (stats.T) と比べる。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), "results/au2");
const rows = new Map();
for (const f of fs.readdirSync(dir).filter((x) => /^(fake|null)_r\d+\.json$/.test(x)).sort()) {
  const cond = f.startsWith("fake") ? "Chrome fake シンク" : "Chrome PulseAudio null-sink";
  for (const x of JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")).results) {
    const r = x.result, s = r?.stats ?? {}, ctx = r?.ctx ?? {};
    const B = r?.cfg?.buf ?? 0, burst = s.burst_obs ?? 0;
    const key = `${cond} | ${r?.sr ?? "-"} | ${x.name}`;
    if (!rows.has(key)) rows.set(key, []);
    rows.get(key).push({
      ok: x.ok, underruns: s.underruns ?? -1, silence: s.silence_frames ?? -1, burst, T: s.T ?? 0, B,
      Treq: B ? Math.ceil((burst * 1.25 + B) / B) * B : 0,
      base: (ctx.baseLatency ?? 0) * 1000, out: (ctx.outputLatency ?? 0) * 1000, clock: r?.clock?.rate_hz ?? 0,
    });
  }
}
const f1 = (v) => v.toFixed(1);
// 最小〜最大 (n=3 のセル内レンジ)。min と max が同じなら単一値
const rng = (lo, hi, fmt = String) => (lo === hi ? fmt(lo) : `${fmt(lo)}〜${fmt(hi)}`);
console.log("| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |");
console.log("|---|---|---|---|---|---|---|---|---|---|---|---|---|");
for (const [key, xs] of rows) {
  const [cond, sr, name] = key.split(" | ");
  const mx = (k) => Math.max(...xs.map((x) => x[k]));
  const mn = (k) => Math.min(...xs.map((x) => x[k]));
  const avg = (k) => xs.reduce((a, x) => a + x[k], 0) / xs.length;
  const pass = xs.filter((x) => x.ok).length;
  const ur = xs.reduce((a, x) => a + x.underruns, 0);
  // T≥T_req は run ごとの判定 (表の脚注参照)。セル最大 burst 基準の判定は REPORT 側に書く
  const tOk = xs.every((x) => x.T >= x.Treq);
  console.log(`| ${cond} | ${sr} | ${name} | ${xs.length} | ${pass}/${xs.length} | ${ur} | ${rng(mn("burst"), mx("burst"))} | ${rng(mn("T"), mx("T"))} | ${mx("Treq")} | ${tOk ? "OK" : "NG"} | ${rng(mn("base"), mx("base"), f1)} | ${rng(mn("out"), mx("out"), f1)} | ${f1(avg("clock"))} |`);
}
