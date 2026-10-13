import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWav, writeWav, compareWav, judge, judgeWav, firstDiff, firstViolation, ulpDistF32 } from '../src/wav.ts';
import { fft, integratedLoudness, truePeakDb, compareStft, stftFrameCount, stftFrameStart } from '../src/stft.ts';
import { parseFlp } from '../src/flp.ts';
import { diffFlp } from '../src/flpdiff.ts';

const sine = (n: number, f: number, amp = 0.5): Float64Array => Float64Array.from({ length: n }, (_, i) => Math.fround(amp * Math.sin((2 * Math.PI * f * i) / 48000)));

test('wav float32 write/parse is lossless and bit-exact compare passes', () => {
  const ch = [sine(4800, 440), sine(4800, 660)];
  const w = parseWav(writeWav(ch, 48000, 32, true));
  assert.equal(w.frames, 4800);
  assert.equal(w.channels, 2);
  assert.deepEqual([...w.ch[0]], [...ch[0]]);
  const m = compareWav(w, parseWav(writeWav(ch, 48000, 32, true)));
  assert.equal(m.bitExact, true);
  assert.equal(judge(m, 'A-exact').pass, true);
});

test('ULP distance and tolerance classes', () => {
  assert.equal(ulpDistF32(1, 1), 0);
  assert.equal(ulpDistF32(1, 1 + 2 ** -23), 1);
  assert.equal(ulpDistF32(0, -0), 0);
  const a = sine(4800, 440);
  const b = a.map((x) => x + (x === 0 ? 0 : Math.sign(x) * 2 ** -24 * Math.abs(x)));
  const m = compareWav(parseWav(writeWav([a], 48000, 32, true)), parseWav(writeWav([b], 48000, 32, true)));
  assert.equal(judge(m, 'A-exact').pass, false);
  assert.equal(judge(m, 'B-ulp').pass, true);
  const c = a.map((x) => x * 1.001);
  const m2 = compareWav(parseWav(writeWav([a], 48000, 32, true)), parseWav(writeWav([c], 48000, 32, true)));
  assert.equal(judge(m2, 'B-ulp').pass, false);
  assert.equal(judge(m2, 'C-statistical').pass, false);
  assert.equal(judge(m2, 'D-spectral').pass, false, 'D-spectral without the STFT stage is fail-closed');
  const w2 = [parseWav(writeWav([a], 48000, 32, true)), parseWav(writeWav([c], 48000, 32, true))] as const;
  assert.equal(judgeWav(w2[0], w2[1], 'D-spectral').verdict.pass, true);
});

test('NaN and shape mismatches always fail', () => {
  const a = parseWav(writeWav([sine(100, 440)], 48000, 32, true));
  const bad = sine(100, 440);
  bad[7] = NaN;
  const b = parseWav(writeWav([bad], 48000, 32, true));
  assert.equal(judgeWav(a, b, 'D-spectral').verdict.pass, false);
  const c = parseWav(writeWav([sine(99, 440)], 48000, 32, true));
  assert.equal(judgeWav(a, c, 'D-spectral').verdict.pass, false);
});

test('pcm16/pcm24 decode', () => {
  const x = Float64Array.from([0, 0.5, -0.5, 0.999]);
  const w16 = parseWav(writeWav([x], 44100, 16, false));
  const w24 = parseWav(writeWav([x], 44100, 24, false));
  assert.ok(Math.abs(w16.ch[0][1] - 0.5) < 1 / 32768);
  assert.ok(Math.abs(w24.ch[0][2] + 0.5) < 1 / 8388608);
});

test('flp diff masks volatile ids and reports the rest', () => {
  const mk = (ver: string, tempo: number): Uint8Array => {
    const v = [...Buffer.from(ver), 0];
    const body = [199, v.length, ...v, 156, tempo & 255, (tempo >> 8) & 255, 0, 0];
    return Uint8Array.from([0x46, 0x4c, 0x68, 0x64, 6, 0, 0, 0, 0, 0, 1, 0, 96, 0, 0x46, 0x4c, 0x64, 0x74, body.length, 0, 0, 0, ...body]);
  };
  const a = parseFlp(mk('25.2.0', 1000));
  assert.equal(diffFlp(a, parseFlp(mk('26.1.7', 1000))).identical, true);
  const d = diffFlp(a, parseFlp(mk('26.1.7', 2000)));
  assert.equal(d.identical, false);
  assert.deepEqual(Object.keys(d.onlyA), ['Tempo(156)']);
});

const SR = 48000;
const tone = (n: number, f: number, amp: number): Float64Array => Float64Array.from({ length: n }, (_, i) => Math.fround(amp * Math.sin((2 * Math.PI * f * i) / SR)));
const noise = (n: number, seed: number, amp = 0.3): Float64Array => {
  let s = seed >>> 0;
  return Float64Array.from({ length: n }, () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return Math.fround(amp * ((s / 0xffffffff) * 2 - 1));
  });
};
const wav = (...ch: Float64Array[]) => parseWav(writeWav(ch, SR, 32, true));
const dbAmp = (d: number) => Math.pow(10, d / 20);

test('fft matches a direct DFT', () => {
  const n = 16;
  const x = Float64Array.from({ length: n }, (_, i) => Math.sin(i * 1.3) + 0.25 * i);
  const re = Float64Array.from(x);
  const im = new Float64Array(n);
  fft(re, im);
  for (let k = 0; k < n; k++) {
    let r = 0;
    let q = 0;
    for (let i = 0; i < n; i++) {
      r += x[i] * Math.cos((2 * Math.PI * k * i) / n);
      q -= x[i] * Math.sin((2 * Math.PI * k * i) / n);
    }
    assert.ok(Math.abs(re[k] - r) < 1e-9 && Math.abs(im[k] - q) < 1e-9, `bin ${k}`);
  }
});

test('LUFS-I: 997 Hz -23 dBFS stereo = -23.0 LUFS (EBU R128 reference), gating and short signals', () => {
  const t = tone(SR * 5, 997, dbAmp(-23));
  assert.ok(Math.abs(integratedLoudness([t, t], SR) + 23) < 0.05);
  // mono at the same level is 3.01 LU quieter
  assert.ok(Math.abs(integratedLoudness([t], SR) - integratedLoudness([t, t], SR) + 3.0103) < 1e-6);
  // 5 s of tone followed by 5 s of -80 dBFS: the quiet part is dropped by the -70 LUFS absolute gate
  const quiet = new Float64Array(SR * 10);
  quiet.set(t);
  quiet.set(tone(SR * 5, 997, dbAmp(-80)), SR * 5);
  assert.ok(Math.abs(integratedLoudness([quiet, quiet], SR) + 23) < 0.3);
  // silence -> -Infinity; < 400 ms still measured
  assert.equal(integratedLoudness([new Float64Array(SR), new Float64Array(SR)], SR), -Infinity);
  assert.ok(Number.isFinite(integratedLoudness([tone(4800, 997, 0.5)], SR)));
});

test('true peak sees inter-sample peaks that sample peak misses', () => {
  // fs/4 sine with 45 degree phase: every sample is +-0.7071*A, true peak is A
  // (Hann envelope: an abruptly starting signal legitimately overshoots at its edges)
  const x = Float64Array.from({ length: 4800 }, (_, i) => Math.fround(Math.sin((Math.PI * i) / 4800) ** 2 * Math.sin((Math.PI / 2) * i + Math.PI / 4)));
  assert.ok(Math.abs(20 * Math.log10(0.7071067811865476) - -3.0103) < 1e-3);
  const tp = truePeakDb([x], SR);
  const sampleDb = 20 * Math.log10(Math.max(...x.map(Math.abs)));
  assert.ok(Math.abs(tp) < 0.05, `true peak ${tp} dBTP`);
  assert.ok(tp > sampleDb + 2.5, `must exceed the ${sampleDb.toFixed(2)} dB sample peak`);
  assert.equal(truePeakDb([new Float64Array(100)], SR), -Infinity);
});

test('stft frame count and silent reference', () => {
  assert.equal(stftFrameCount(0), 0);
  assert.equal(stftFrameCount(100), 1);
  assert.equal(stftFrameCount(4096), 1);
  assert.equal(stftFrameCount(4097), 2);
  assert.equal(stftFrameCount(4096 + 2048), 3);
  assert.equal(stftFrameStart(2, 4096 + 2048), 2048, 'last frame is end-aligned (full window)');
  assert.equal(stftFrameStart(1, 100), 0);
  const z = new Float64Array(8192);
  const r = compareStft([z], [z], SR);
  assert.equal(r.refSilent, true);
  assert.equal(judgeWav(wav(z), wav(z), 'D-spectral').verdict.pass, true);
  assert.equal(judgeWav(wav(z), wav(tone(8192, 440, 0.1)), 'D-spectral').verdict.pass, false);
});

test('D-spectral: random-phase / different-noise passes only if the spectrum agrees, gain and tone errors fail', () => {
  const n = SR * 2;
  const ref = tone(n, 1000, 0.5);
  // +0.005 dB gain: inside every tolerance (incl. rmsDiff/ref <= -60 dB) -> PASS
  const near = ref.map((v) => Math.fround(v * dbAmp(0.005)));
  const ok = judgeWav(wav(ref, ref), wav(near, near), 'D-spectral');
  assert.equal(ok.verdict.pass, true, ok.verdict.why);
  assert.equal(ok.spectral!.stft.first, null);
  // +0.5 dB gain: STFT / LUFS / TP all out -> FAIL, first diff at frame 0
  const loud = ref.map((v) => Math.fround(v * dbAmp(0.5)));
  const bad = judgeWav(wav(ref), wav(loud), 'D-spectral');
  assert.equal(bad.verdict.pass, false);
  assert.equal(bad.spectral!.stft.first!.frame, 0);
  assert.ok(Math.abs(bad.spectral!.lufsDiff - 0.5) < 0.01);
  assert.ok(Math.abs(bad.spectral!.truePeakDiff - 0.5) < 0.05);
  // phase-shifted tone has the same magnitude spectrum, the same LUFS and peak: STFT stage passes
  const shifted = Float64Array.from({ length: n }, (_, i) => Math.fround(0.5 * Math.sin((2 * Math.PI * 1000 * i) / SR + 1.1)));
  const ph = judgeWav(wav(ref), wav(shifted), 'D-spectral');
  assert.equal(ph.spectral!.stft.binsOverTol, 0, ph.verdict.why);
  assert.ok(Math.abs(ph.spectral!.lufsDiff) < 0.1);
});

test('D-spectral: tolerates sub-floor error but not an in-band bin error; bins below -60 dB are ignored', () => {
  const n = SR * 2;
  const ref = tone(n, 1000, 0.5);
  // add a -80 dBFS tone at 6 kHz: > 60 dB below the 1 kHz peak, so not compared
  const hid = Float64Array.from(ref, (v, i) => Math.fround(v + dbAmp(-80) * Math.sin((2 * Math.PI * 6000 * i) / SR)));
  const r1 = compareStft([ref], [hid], SR);
  assert.equal(r1.binsOverTol, 0);
  // add a -20 dBFS tone at 6 kHz: shows up in test but its ref bins are below the floor too; reverse (ref has it) must be compared
  const withTone = Float64Array.from(ref, (v, i) => Math.fround(v + 0.05 * Math.sin((2 * Math.PI * 6000 * i) / SR)));
  const r2 = compareStft([withTone], [ref], SR);
  assert.ok(r2.binsOverTol > 0);
  assert.ok(Math.abs(r2.first!.freqHz - 6000) <= 12, `first bad bin at ${r2.first!.freqHz} Hz`);
});

test('first-difference position: sample domain and STFT frame', () => {
  const n = SR;
  const a = tone(n, 440, 0.4);
  const bArr = Float64Array.from(a);
  bArr[30000] = Math.fround(bArr[30000] + 0.01);
  const A = wav(a, a);
  const B = wav(a, bArr);
  const d = firstDiff(A, B)!;
  assert.deepEqual([d.frame, d.channel], [30000, 1]);
  assert.ok(Math.abs(d.timeSec - 30000 / SR) < 1e-12);
  assert.equal(firstDiff(A, A), null);
  assert.equal((firstViolation(A, B, 'A-exact') as { frame: number }).frame, 30000);
  assert.equal(firstViolation(A, B, 'B-ulp') !== null, true);
  // a burst starting at 0.5 s: the first failing STFT frame is the first window that touches it
  const burst = Float64Array.from(a);
  for (let i = 24000; i < 24000 + 2048; i++) burst[i] = Math.fround(burst[i] + 0.2 * Math.sin(i * 0.9));
  const r = judgeWav(wav(a), wav(burst), 'D-spectral');
  assert.equal(r.verdict.pass, false);
  const f = r.spectral!.stft.first!;
  assert.equal(f.frame, Math.floor((24000 - 4096) / 1024) + 1);
  assert.ok(f.startSample <= 24000 && f.startSample + 4096 > 24000);
  assert.ok(r.verdict.why.includes(`first@frame=${f.frame}`));
  assert.equal(firstViolation(A, B, 'D-spectral', r.spectral), r.spectral!.stft.first);
});

test('D-spectral: uncorrelated noise with equal spectrum is rejected (per-bin magnitudes differ)', () => {
  const r = judgeWav(wav(noise(SR, 1)), wav(noise(SR, 2)), 'D-spectral');
  assert.equal(r.verdict.pass, false);
  assert.ok(Math.abs(r.spectral!.lufsDiff) < 0.5);
});
