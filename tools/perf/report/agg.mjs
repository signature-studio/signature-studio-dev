// results/*.jsonl の集計ユーティリティ
import fs from 'node:fs';
export const R = new URL('../results/', import.meta.url).pathname;
export function readJsonl(name) {
  const f = R + name; if (!fs.existsSync(f)) return [];
  return fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
}
export const med = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : NaN; };
export const min = (a) => Math.min(...a);
export function group(rows, keyf) {
  const m = new Map();
  for (const r of rows) { if (r.error) continue; const k = keyf(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); }
  return m;
}
export const f = (x, d = 3) => (x == null || Number.isNaN(x) ? '-' : Number(x).toFixed(d));
export function summarize(rows) {   // 同一(kind,variant,mode) の反復を集約
  const p50s = rows.map((r) => r.steady.p50), p99s = rows.map((r) => r.steady.p99);
  const o = {
    n: rows.length, wasmBytes: rows[0].wasmBytes, p50: med(p50s), p50min: min(p50s), p99: med(p99s), p999: med(rows.map((r) => r.steady.p999)),
    max: med(rows.map((r) => r.steady.max)), createMs: med(rows.map((r) => r.createMs)), firstCall: med(rows.map((r) => r.firstCallMs)),
    sigs: [...new Set(rows.map((r) => r.signature))], load: med(rows.map((r) => r.load ?? 0)),
    rss: med(rows.map((r) => r.rendererHwmMB ?? r.rssEndMB ?? NaN)),
  };
  const b = rows.filter((r) => r.batch64).map((r) => r.batch64.p50); o.p50b = b.length ? med(b) : NaN;
  if (Number.isFinite(o.p50b) && o.p50 < 0.02) { o.p50 = o.p50b; o.p50min = Math.min(...b); o.batched = true; }
  o.rtf44 = o.p50 / (128 / 44100 * 1000); o.rtf48 = o.p50 / (128 / 48000 * 1000);
  o.rtf44p99 = o.p99 / (128 / 44100 * 1000); o.rtf44min = o.p50min / (128 / 44100 * 1000);
  return o;
}
