// L-3 (#104): decode event 213 of the top native plugins over a corpus tree and verify the layouts.
// usage: node cli/plugstate.ts [dir] [out.json]   (dir = FLhd-containing tree; default FL_ROOT env, or a flat dir of block*_DATA.bin)
import { readdirSync, readFileSync, writeFileSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { join } from 'node:path';
import { parseFlp, isFlpMagic } from '../src/flp.ts';
import { decodePluginState, encodePluginState, hasLayout, predictedLength, versionSupported, LAYOUTS } from '../src/plugstate.ts';

function* walk(dir: string): Generator<string> {
  for (const n of readdirSync(dir).sort()) {
    const p = join(dir, n);
    const st = statSync(p);
    if (st.isDirectory()) yield* walk(p);
    else if (st.isFile() && st.size >= 4) yield p;
  }
}
const u16 = (d: Uint8Array): string => {
  let s = '';
  for (let i = 0; i + 1 < d.length; i += 2) { const c = d[i] | (d[i + 1] << 8); if (!c) break; s += String.fromCharCode(c); }
  return s;
};
const a8 = (d: Uint8Array): string => { let s = ''; for (const b of d) { if (!b) break; s += String.fromCharCode(b); } return s; };

interface Stat {
  events: number; supported: number; legacy: number; ok: number; roundTrip: number; lengthMatch: number; lengthChecked: number;
  versions: Record<string, number>; bad: string[];
}
const dir = process.argv[2] ?? process.env.FL_ROOT;
if (!dir) { console.error('usage: node cli/plugstate.ts <dir> [out.json]'); process.exit(2); }
const stats: Record<string, Stat> = {};
for (const k of Object.keys(LAYOUTS)) stats[k] = { events: 0, supported: 0, legacy: 0, ok: 0, roundTrip: 0, lengthMatch: 0, lengthChecked: 0, versions: {}, bad: [] };
let files = 0;
for (const p of walk(dir)) {
  const fd = openSync(p, 'r'); const head = new Uint8Array(4); readSync(fd, head, 0, 4, 0); closeSync(fd);
  if (!isFlpMagic(head)) continue;
  let f;
  try { f = parseFlp(readFileSync(p)); } catch { continue; }
  files++;
  let cur = '';
  for (const e of f.events) {
    if (e.ext) continue;
    if (e.id === 201) { const d = e.data; cur = d.length >= 2 && d[1] === 0 ? u16(d) : a8(d); }
    if (e.id !== 213 || !hasLayout(cur)) continue;
    const st = stats[cur];
    st.events++;
    const s = decodePluginState(cur, e.data)!;
    const vk = String(s.version);
    st.versions[vk] = (st.versions[vk] ?? 0) + 1;
    if (!versionSupported(cur, s.versionRaw)) st.legacy++;
    else {
      st.supported++;
      if (s.ok) st.ok++; else if (st.bad.length < 5) st.bad.push(`${p.split('/').pop()}:v${s.version}:${e.data.length}B`);
    }
    const re = encodePluginState(s);
    if (re.length === e.data.length && re.every((b, i) => b === e.data[i])) st.roundTrip++;
    const pl = predictedLength(cur, s.versionRaw);
    if (pl !== undefined) { st.lengthChecked++; if (pl === e.data.length) st.lengthMatch++; }
  }
}
console.log(`files scanned: ${files}`);
let allOk = true;
for (const [k, st] of Object.entries(stats)) {
  console.log(`${k.padEnd(24)} events=${st.events} supported=${st.supported} layoutOk=${st.ok} legacy(raw)=${st.legacy} roundTrip=${st.roundTrip} predictedLen=${st.lengthMatch}/${st.lengthChecked} versions=${JSON.stringify(st.versions)}${st.bad.length ? ' BAD=' + st.bad.join(',') : ''}`);
  if (st.events === 0 || st.ok !== st.supported || st.roundTrip !== st.events || st.lengthMatch !== st.lengthChecked) allOk = false;
}
if (process.argv[3]) writeFileSync(process.argv[3], JSON.stringify({ files, stats }, null, 1) + '\n');
process.exit(allOk ? 0 : 1);
