// Compare two WAV files under an oracle tolerance class; also prints the determinism hash of each.
// D-spectral additionally runs the STFT / LUFS-I / true-peak stage (ORACLE.md 4.4). `firstDiff` is the first position that violates the class.
// usage: node cli/wavcmp.ts a.wav b.wav [A-exact|B-ulp|C-statistical|D-spectral]
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { parseWav, judgeWav, firstViolation, type ToleranceClass } from '../src/wav.ts';

const [fa, fb, cls = 'A-exact'] = process.argv.slice(2);
if (!fa || !fb) {
  console.error('usage: node cli/wavcmp.ts a.wav b.wav [A-exact|B-ulp|C-statistical|D-spectral]');
  process.exit(2);
}
const a = parseWav(readFileSync(fa));
const b = parseWav(readFileSync(fb));
const { metrics: m, spectral, verdict: v } = judgeWav(a, b, cls as ToleranceClass);
const sha = (w: typeof a) => createHash('sha256').update(w.raw).digest('hex');
const firstDiff = m.sameShape && m.nanOrInf === 0 ? firstViolation(a, b, cls as ToleranceClass, spectral) : null;
const num = (x: number) => (Number.isFinite(x) ? x : String(x));
const sp = spectral && {
  lufsA: num(spectral.lufsA),
  lufsB: num(spectral.lufsB),
  lufsDiff: num(spectral.lufsDiff),
  truePeakA: num(spectral.truePeakA),
  truePeakB: num(spectral.truePeakB),
  truePeakDiff: num(spectral.truePeakDiff),
  stft: { ...spectral.stft, first: spectral.stft.first, worst: spectral.stft.worst, refPeakDb: num(spectral.stft.refPeakDb), maxDiffDb: num(spectral.stft.maxDiffDb) },
};
console.log(
  JSON.stringify(
    { a: { frames: a.frames, ch: a.channels, rate: a.sampleRate, bits: a.bits, sha256: sha(a) }, b: { frames: b.frames, ch: b.channels, rate: b.sampleRate, bits: b.bits, sha256: sha(b) }, metrics: m, spectral: sp, firstDiff, verdict: v },
    (_k, x) => (typeof x === 'number' && !Number.isFinite(x) ? String(x) : x),
    1,
  ),
);
process.exit(v.pass ? 0 : 1);
