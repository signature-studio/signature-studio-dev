// Win installer (block_manifest.json DATA blocks starting with "FLhd") vs mac corpus: which FL files exist only on win?
// usage: node cli/winmac.ts [out.json]
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { parseFlp, writeFlp, firstDiff } from '../src/flp.ts';
import { summarize } from '../src/summary.ts';
import { listFlhdFiles } from './_corpus.ts';

const WIN = process.env.WIN_ROOT ?? '/home/ubuntu/work/analysis/win64';
const man = JSON.parse(readFileSync(`${WIN}/block_manifest.json`, 'utf8')) as { idx: number; kind: string; path: string; dsize: number }[];
const macHashes = new Set(listFlhdFiles().map((f) => createHash('sha256').update(readFileSync(f.abs)).digest('hex')));
let winFlhd = 0;
let roundtripOk = 0;
const winOnly: unknown[] = [];
const fmt: Record<string, number> = {};
for (const b of man) {
  if (b.kind !== 'DATA') continue;
  const buf = readFileSync(b.path);
  if (buf.length < 4 || buf.toString('latin1', 0, 4) !== 'FLhd') continue;
  winFlhd++;
  const p = parseFlp(buf);
  if (firstDiff(buf, writeFlp(p)) < 0) roundtripOk++;
  const h = createHash('sha256').update(buf).digest('hex');
  if (!macHashes.has(h)) {
    const s = summarize(p);
    fmt[s.formatName] = (fmt[s.formatName] ?? 0) + 1;
    winOnly.push({ block: b.idx, size: buf.length, format: s.formatName, version: s.version, events: s.events, plugin: s.plugins[0]?.key ?? null, channels: s.channels, inserts: s.inserts });
  }
}
const res = { winFlhdBlocks: winFlhd, roundtripOk, macFlhdFiles: macHashes.size, winOnly: winOnly.length, winOnlyByFormat: fmt, winOnlyList: winOnly };
console.log(JSON.stringify({ ...res, winOnlyList: undefined }));
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(res, null, 1));
