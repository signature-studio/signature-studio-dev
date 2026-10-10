import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFlp, writeFlp, encodeVarint, firstDiff, FlpParseError, type FlpFile } from '../src/flp.ts';

function build(events: number[][], format = 0, hdrExtra: number[] = []): Uint8Array {
  const body = events.flat();
  const hdrLen = 6 + hdrExtra.length;
  const out = [0x46, 0x4c, 0x68, 0x64, hdrLen, 0, 0, 0, format, 0, 1, 0, 96, 0, ...hdrExtra, 0x46, 0x4c, 0x64, 0x74, body.length & 255, (body.length >> 8) & 255, 0, 0, ...body];
  return Uint8Array.from(out);
}

test('varint encode/decode boundaries', () => {
  assert.deepEqual([...encodeVarint(0)], [0]);
  assert.deepEqual([...encodeVarint(127)], [127]);
  assert.deepEqual([...encodeVarint(128)], [0x80, 1]);
  assert.deepEqual([...encodeVarint(300)], [0xac, 2]);
  assert.deepEqual([...encodeVarint(2 ** 21)], [0x80, 0x80, 0x80, 1]);
});

test('all four payload classes parse and round-trip', () => {
  const buf = build([[9, 1], [64, 5, 0], [156, 0x10, 0x27, 0, 0], [199, 3, 0x31, 0x2e, 0], [213, 2, 7, 8]]);
  const f = parseFlp(buf);
  assert.equal(f.events.length, 5);
  assert.deepEqual(f.events.map((e) => e.data.length), [1, 2, 4, 3, 2]);
  assert.equal(firstDiff(buf, writeFlp(f)), -1);
});

test('extended 0xAC event: u32 id then class-driven payload', () => {
  // 0xC0000101 text (varlen), 0x00000100 byte, 0x40000200 word, 0x80000300 dword
  const buf = build([
    [0xac, 0x01, 0x01, 0x00, 0xc0, 4, 65, 0, 66, 0],
    [0xac, 0x00, 0x01, 0x00, 0x00, 9],
    [0xac, 0x00, 0x02, 0x00, 0x40, 1, 2],
    [0xac, 0x00, 0x03, 0x00, 0x80, 1, 2, 3, 4],
    [37, 1],
  ]);
  const f = parseFlp(buf);
  assert.deepEqual(f.events.map((e) => [e.id, e.data.length, !!e.ext]), [[0xc0000101, 4, true], [0x100, 1, true], [0x40000200, 2, true], [0x80000300, 4, true], [37, 1, false]]);
  assert.equal(f.dtSlack.length, 0);
  assert.equal(firstDiff(buf, writeFlp(f)), -1);
});

test('non-canonical varint length is preserved byte-exactly', () => {
  const buf = build([[213, 0x81, 0x00, 7]]);
  const f = parseFlp(buf);
  assert.equal(f.events[0].data.length, 1);
  assert.deepEqual([...(f.events[0].lenEnc ?? [])], [0x81, 0x00]);
  assert.equal(firstDiff(buf, writeFlp(f)), -1);
});

test('truncated event goes to dtSlack and survives write', () => {
  const buf = build([[9, 1], [213, 10, 1, 2]]);
  const f = parseFlp(buf);
  assert.equal(f.events.length, 1);
  assert.equal(f.dtSlack.length, 4);
  assert.equal(firstDiff(buf, writeFlp(f)), -1);
});

test('trailer and header extension survive', () => {
  const buf = Uint8Array.from([...build([[9, 1]], 0x30, [1, 2]), 0xde, 0xad]);
  const f = parseFlp(buf);
  assert.deepEqual([...f.trailer], [0xde, 0xad]);
  assert.deepEqual([...f.header.hdrExtra], [1, 2]);
  assert.equal(f.header.format, 0x30);
  assert.equal(firstDiff(buf, writeFlp(f)), -1);
});

test('bad magic is rejected; edited event is reflected in output', () => {
  assert.throws(() => parseFlp(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])), FlpParseError);
  const f: FlpFile = parseFlp(build([[156, 0x10, 0x27, 0, 0]]));
  f.events[0] = { ...f.events[0], data: Uint8Array.from([0x20, 0x4e, 0, 0]) };
  const g = parseFlp(writeFlp(f));
  assert.equal(new DataView(g.events[0].data.buffer, g.events[0].data.byteOffset, 4).getUint32(0, true), 20000);
});
