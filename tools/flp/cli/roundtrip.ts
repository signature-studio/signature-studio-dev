// Round-trip every FLhd file.
//  level 0: container  parse -> write -> byte compare
//  level 1: typed      every event decode -> encode == payload
// usage: node cli/roundtrip.ts [out.json]
import { readFileSync, writeFileSync } from 'node:fs';
import { parseFlp, writeFlp, firstDiff } from '../src/flp.ts';
import { typedRoundTrip } from '../src/decode.ts';
import { listFlhdFiles } from './_corpus.ts';

const out = process.argv[2];
const files = listFlhdFiles();
const per: Record<string, { n: number; l0ok: number; l1ok: number; events: number; typedMismatchEvents: number }> = {};
const bad: unknown[] = [];
let totalBytes = 0;
let totalEvents = 0;
const t0 = performance.now();
for (const f of files) {
  const buf = readFileSync(f.abs);
  totalBytes += buf.length;
  const g = (per[f.group] ??= { n: 0, l0ok: 0, l1ok: 0, events: 0, typedMismatchEvents: 0 });
  g.n++;
  try {
    const p = parseFlp(buf);
    g.events += p.events.length;
    totalEvents += p.events.length;
    const d = firstDiff(buf, writeFlp(p));
    if (d < 0) g.l0ok++;
    else bad.push({ rel: f.rel, level: 0, firstDiff: d, warnings: p.warnings });
    const t = typedRoundTrip(p);
    if (t.mismatches.length === 0) g.l1ok++;
    else {
      g.typedMismatchEvents += t.mismatches.length;
      bad.push({ rel: f.rel, level: 1, mismatches: t.mismatches.slice(0, 5), count: t.mismatches.length });
    }
  } catch (e) {
    bad.push({ rel: f.rel, error: String(e) });
  }
}
const ms = performance.now() - t0;
const sum = (k: 'n' | 'l0ok' | 'l1ok') => Object.values(per).reduce((a, b) => a + b[k], 0);
const res = {
  total: files.length,
  totalBytes,
  totalEvents,
  level0: { ok: sum('l0ok'), rate: sum('l0ok') / files.length },
  level1: { ok: sum('l1ok'), rate: sum('l1ok') / files.length },
  ms: Math.round(ms),
  per,
  badCount: bad.length,
  bad: bad.slice(0, 30),
};
console.log(JSON.stringify(res, null, 1));
if (out) writeFileSync(out, JSON.stringify(res, null, 1));
