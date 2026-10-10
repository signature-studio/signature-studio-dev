// Compare two WAV files under an oracle tolerance class; also prints the determinism hash of each.
// usage: node cli/wavcmp.ts a.wav b.wav [A-exact|B-ulp|C-statistical|D-spectral]
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { parseWav, compareWav, judge, type ToleranceClass } from '../src/wav.ts';

const [fa, fb, cls = 'A-exact'] = process.argv.slice(2);
if (!fa || !fb) {
  console.error('usage: node cli/wavcmp.ts a.wav b.wav [A-exact|B-ulp|C-statistical|D-spectral]');
  process.exit(2);
}
const a = parseWav(readFileSync(fa));
const b = parseWav(readFileSync(fb));
const m = compareWav(a, b);
const v = judge(m, cls as ToleranceClass);
const sha = (w: typeof a) => createHash('sha256').update(w.raw).digest('hex');
console.log(JSON.stringify({ a: { frames: a.frames, ch: a.channels, rate: a.sampleRate, bits: a.bits, sha256: sha(a) }, b: { frames: b.frames, ch: b.channels, rate: b.sampleRate, bits: b.bits, sha256: sha(b) }, metrics: m, verdict: v }, null, 1));
process.exit(v.pass ? 0 : 1);
