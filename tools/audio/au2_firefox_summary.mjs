// AU-2 Firefox 行列の集計: results/au2/firefox_r<rep>.json を読み、条件ごとの PASS 数と min–max を Markdown 表で出す (REPORT_AU2_CI.md §9-1 の元)。
// Chrome 側の集計は au2_summary.mjs (fake_r*・null_r*)。同じディレクトリを読むため、ファイル名で分ける。
// 使い方: node tools/audio/au2_firefox_summary.mjs [results ディレクトリ (既定 results/au2)]
// 既定出力の接続は sink_route (旧 JSON は pulse_sink_input・on_ci_null) を読む
import fs from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
const dir = process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), "results/au2");
const route = (x) => x.sink_route ?? x.pulse_sink_input;
const onExpected = (x) => route(x)?.on_expected ?? route(x)?.on_ci_null;
const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /^firefox_r\d+\.json$/.test(f)).sort() : [];
const rows = new Map();
const range = (xs) => { const v = xs.filter(Number.isFinite); if (!v.length) return "-"; const a = Math.min(...v), b = Math.max(...v); return a === b ? `${a}` : `${a}–${b}`; };
for (const f of files) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
  for (const r of d.results) {
    const k = `${d.browser}|${r.sr}|${r.name}`;
    if (!rows.has(k)) rows.set(k, { browser: d.browser, sr: r.sr, name: r.name, runs: [] });
    rows.get(k).runs.push({ ...r, rep: d.rep });
  }
}
console.log("| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | 既定出力 (期待 sink) に接続 | sink-input の規格 |");
console.log("|---|---|---|---|---|---|---|---|---|---|---|---|---|");
for (const { browser, sr, name, runs } of rows.values()) {
  const pass = runs.filter((x) => x.ok).length;
  const conn = runs.filter(onExpected).length;
  const specs = [...new Set(runs.flatMap((x) => route(x)?.specs ?? []))].join(", ");
  console.log(`| ${browser} | ${sr} | ${name} | ${runs.length} | ${pass}/${runs.length} | ${range(runs.map((x) => x.underruns))} | ${range(runs.map((x) => x.burst))} | ${range(runs.map((x) => x.T))} | ${range(runs.map((x) => (x.clock_hz == null ? null : Math.round(x.clock_hz))))} | ${range(runs.map((x) => x.ctx?.baseLatency))} | ${range(runs.map((x) => x.ctx?.outputLatency))} | ${conn}/${runs.length} | ${specs} |`);
}
for (const f of files) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
  console.log(`\n${f}: ${JSON.stringify(d.probe)}`);
}
