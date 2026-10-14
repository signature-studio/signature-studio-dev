// AU-2 行列の集計: results/au2/<browser>_r<rep>.json を読み、条件ごとの PASS 数と min–max を Markdown 表で出す (REPORT_AU2_CI.md §5-1 の元)。
// 使い方: node tools/audio/au2_summary.mjs
import fs from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "results/au2");
const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /^[a-z]+_r\d+\.json$/.test(f)).sort() : [];
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
console.log("| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | sink-input が ci_null に接続 | sink-input の規格 |");
console.log("|---|---|---|---|---|---|---|---|---|---|---|---|---|");
for (const { browser, sr, name, runs } of rows.values()) {
  const pass = runs.filter((x) => x.ok).length;
  const conn = runs.filter((x) => x.pulse_sink_input?.on_ci_null).length;
  const specs = [...new Set(runs.flatMap((x) => x.pulse_sink_input?.specs ?? []))].join(", ");
  console.log(`| ${browser} | ${sr} | ${name} | ${runs.length} | ${pass}/${runs.length} | ${range(runs.map((x) => x.underruns))} | ${range(runs.map((x) => x.burst))} | ${range(runs.map((x) => x.T))} | ${range(runs.map((x) => (x.clock_hz == null ? null : Math.round(x.clock_hz))))} | ${range(runs.map((x) => x.ctx?.baseLatency))} | ${range(runs.map((x) => x.ctx?.outputLatency))} | ${conn}/${runs.length} | ${specs} |`);
}
for (const f of files) {
  const d = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
  console.log(`\n${f}: ${JSON.stringify(d.probe)}`);
}
