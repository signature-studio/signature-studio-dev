import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decodePluginState, encodePluginState, predictedLength, versionSupported, hasLayout } from '../src/plugstate.ts';

function le32(...v: number[]): Uint8Array {
  const o = new Uint8Array(4 * v.length);
  const dv = new DataView(o.buffer);
  v.forEach((x, i) => dv.setInt32(4 * i, x, true));
  return o;
}
const cat = (...a: Uint8Array[]): Uint8Array => {
  const o = new Uint8Array(a.reduce((n, x) => n + x.length, 0));
  let p = 0;
  for (const x of a) { o.set(x, p); p += x.length; }
  return o;
};

test('predicted lengths follow the SaveRestoreState write sequence', () => {
  assert.equal(predictedLength('Fruity Delay 3', 1), 108);
  assert.equal(predictedLength('Fruity Reeverb 2', 10001), 66);
  assert.equal(predictedLength('Fruity Reeverb 2', 10000), 58);
  assert.equal(predictedLength('Fruity Limiter', 7), 169);
  assert.equal(predictedLength('Fruity Limiter', 6), 168);
  assert.equal(predictedLength('Fruity Parametric EQ 2', 8), 354);
  assert.equal(predictedLength('Fruity Parametric EQ 2', 7), 354);
  assert.equal(predictedLength('Fruity Parametric EQ 2', 6), 350);
  assert.equal(predictedLength('Fruity Parametric EQ 2', 3), 309);
});

test('Delay 3 decode/encode is lossless and names fields', () => {
  const raw = cat(le32(1), le32(...Array.from({ length: 26 }, (_, i) => i * 7 - 3)));
  const s = decodePluginState('Fruity Delay 3', raw)!;
  assert.ok(s.ok);
  assert.equal(s.version, 1);
  assert.deepEqual((s.fields[0].value as number[]).slice(0, 3), [-3, 4, 11]);
  assert.deepEqual([...encodePluginState(s)], [...raw]);
});

test('Maximus keeps the version in the high word and the band streams as tail', () => {
  const raw = cat(le32(0xf0003), le32(...Array.from({ length: 126 }, (_, i) => i)), Uint8Array.from([1, 0]), le32(1, 2), Uint8Array.from([0x11]), le32(1, 2, 3, 4, 5, 6), Uint8Array.from([9, 9, 9]));
  const s = decodePluginState('Maximus', raw)!;
  assert.equal(s.version, 15);
  assert.ok(s.ok);
  assert.equal(s.tail.length, 3);
  assert.deepEqual([...encodePluginState(s)], [...raw]);
});

test('unsupported / short payloads are never lossy (ok=false, bytes preserved)', () => {
  const legacy = cat(le32(2), new Uint8Array(301));
  const s = decodePluginState('Fruity Parametric EQ 2', legacy)!;
  assert.equal(versionSupported('Fruity Parametric EQ 2', 2), false);
  assert.deepEqual([...encodePluginState(s)], [...legacy]);
  const short = cat(le32(8), new Uint8Array(40));
  const t = decodePluginState('Fruity Parametric EQ 2', short)!;
  assert.equal(t.ok, false);
  assert.deepEqual([...encodePluginState(t)], [...short]);
  assert.equal(decodePluginState('Fruity Limiter', new Uint8Array(2))!.ok, false);
  for (const plugin of ['Fruity Delay 3', 'Fruity Reeverb 2', 'Fruity Limiter', 'Fruity Parametric EQ 2', 'Maximus']) {
    for (let n = 0; n < 4; n++) {
      const raw = Uint8Array.from({ length: n }, (_, i) => i + 1);
      const h = decodePluginState(plugin, raw)!;
      assert.equal(h.ok, false, `${plugin} len ${n}`);
      assert.deepEqual([...encodePluginState(h)], [...raw], `${plugin} len ${n}`);
    }
  }
  assert.equal(decodePluginState('3x Osc', new Uint8Array(8)), undefined);
  assert.equal(hasLayout('toString'), false);
});

test('negative control: a wrong layout length is detected (payload with an extra byte is not ok)', () => {
  const raw = cat(le32(1), new Uint8Array(104), Uint8Array.from([0]));
  assert.equal(decodePluginState('Fruity Delay 3', raw)!.ok, false);
  const exact = cat(le32(1), new Uint8Array(104));
  assert.equal(decodePluginState('Fruity Delay 3', exact)!.ok, true);
});
