import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWav, writeWav, compareWav, judge, ulpDistF32 } from '../src/wav.ts';
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
  assert.equal(judge(m2, 'D-spectral').pass, true);
});

test('NaN and shape mismatches always fail', () => {
  const a = parseWav(writeWav([sine(100, 440)], 48000, 32, true));
  const bad = sine(100, 440);
  bad[7] = NaN;
  const b = parseWav(writeWav([bad], 48000, 32, true));
  assert.equal(judge(compareWav(a, b), 'D-spectral').pass, false);
  const c = parseWav(writeWav([sine(99, 440)], 48000, 32, true));
  assert.equal(judge(compareWav(a, c), 'D-spectral').pass, false);
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
