import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFlp } from '../src/flp.ts';
import { decodeText, encodeText, parseVersionString, textIsUtf16, playlistStride, typedRoundTrip, decodeStruct, encodeStruct, LAYOUTS } from '../src/decode.ts';
import { defOf } from '../src/events.ts';
import { parseWrapperData, summarize } from '../src/summary.ts';

test('text encoding switches to UTF-16 at FL 11.5 (not 11.50)', () => {
  assert.equal(textIsUtf16(defOf(203), 203, parseVersionString('11.0.4')), false);
  assert.equal(textIsUtf16(defOf(203), 203, parseVersionString('11.5.13')), true);
  assert.equal(textIsUtf16(defOf(203), 203, parseVersionString('12.3.0.72')), true);
  assert.equal(textIsUtf16(defOf(199), 199, parseVersionString('25.2.3.5164')), false);
  assert.equal(textIsUtf16(defOf(231), 231, parseVersionString('3.0.0')), true);
});

test('UTF-16 text round-trips including lone surrogates and trailing bytes', () => {
  const raw = Uint8Array.from([0x41, 0, 0x00, 0xd8, 0x42, 0, 0, 0, 0xff, 0xff]);
  const t = decodeText(raw, true);
  assert.equal(t.text, 'A\ud800B');
  assert.deepEqual([...encodeText(t, true)], [...raw]);
});

test('struct layout is lossless including unnamed bytes', () => {
  const raw = Uint8Array.from({ length: 24 }, (_, i) => (i * 37 + 5) & 255);
  const v = decodeStruct(raw, LAYOUTS[224]);
  assert.deepEqual([...encodeStruct(v, LAYOUTS[224])], [...raw]);
  assert.equal(v.fields.position, new DataView(raw.buffer).getUint32(0, true));
});

test('playlist stride follows the measured FL version table', () => {
  const v = (s: string) => parseVersionString(s);
  assert.equal(playlistStride(new Uint8Array(0), v('20.8.0.1377')), 32);
  assert.equal(playlistStride(new Uint8Array(0), v('20.99.3000.3031')), 60);
  assert.equal(playlistStride(new Uint8Array(0), v('24.1.0.4212')), 60);
  assert.equal(playlistStride(new Uint8Array(0), v('24.2.99.4720')), 80);
  assert.equal(playlistStride(new Uint8Array(0), v('25.2.5')), 80);
  assert.equal(playlistStride(new Uint8Array(0), v('24.2.99.4701')), 60);
});

test('VST wrapper chunk list parses (version 8, class 10 record, name/vendor)', () => {
  const rec = (id: number, s: string): number[] => {
    const b = [...Buffer.from(s)];
    return [id, 0, 0, 0, b.length, 0, 0, 0, 0, 0, 0, 0, ...b];
  };
  const d = Uint8Array.from([8, 0, 0, 0, 50, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 0, ...rec(54, 'OTT'), ...rec(56, 'Xfer')]);
  const v = parseWrapperData(d);
  assert.equal(v?.version, 8);
  assert.equal(v?.plugclass, 10);
  assert.equal(v?.name, 'OTT');
  assert.equal(v?.vendor, 'Xfer');
  assert.equal(v?.vstVersion, 1);
  assert.equal(parseWrapperData(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])), undefined);
  assert.equal(parseWrapperData(Uint8Array.from([13, 0, 0, 0, ...rec(54, 'OTT')])), undefined);
});

test('wrapper chunk: record 50 absent keeps class 0; truncated record is rejected', () => {
  const rec = (id: number, s: string): number[] => {
    const b = [...Buffer.from(s)];
    return [id, 0, 0, 0, b.length, 0, 0, 0, 0, 0, 0, 0, ...b];
  };
  const v = parseWrapperData(Uint8Array.from([8, 0, 0, 0, ...rec(54, 'OTT')]));
  assert.equal(v?.plugclass, 0);
  assert.equal(parseWrapperData(Uint8Array.from([8, 0, 0, 0, 54, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0, 1])), undefined);
});

test('typed round trip + summary on a synthetic project', () => {
  const t = (id: number, s: string) => [id, s.length * 2 + 2, ...[...s].flatMap((c) => [c.charCodeAt(0), 0]), 0, 0];
  const ev = [[199, 7, 0x32, 0x35, 0x2e, 0x31, 0x2e, 0x30, 0], [156, 0x20, 0x4e, 1, 0], [64, 0, 0], [21, 2], ...[t(201, 'Sytrus')], ...[t(203, 'Lead')], [98, 3, 0], ...[t(201, 'Fruity Limiter')]];
  const body = ev.flat();
  const buf = Uint8Array.from([0x46, 0x4c, 0x68, 0x64, 6, 0, 0, 0, 0, 0, 1, 0, 96, 0, 0x46, 0x4c, 0x64, 0x74, body.length, 0, 0, 0, ...body]);
  const f = parseFlp(buf);
  assert.equal(typedRoundTrip(f).mismatches.length, 0);
  const s = summarize(f);
  assert.equal(s.tempo, 85.536);
  assert.deepEqual(s.plugins.map((p) => [p.where, p.key]), [['channel', 'Sytrus'], ['slot', 'Fruity Limiter']]);
});
