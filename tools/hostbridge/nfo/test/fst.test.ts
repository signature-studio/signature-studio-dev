import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFlp, writeFlp, firstDiff } from '../../../flp/src/flp.ts';
import { parseWrapperData } from '../../../flp/src/summary.ts';
import { buildWrapperFst, buildWrapperChunk, assembleFst } from '../src/fst.ts';
import { tuidFromHex } from '../src/format.ts';
import { FL_ROOT, HAVE_FL, filesWithExt, read } from './_fl.ts';

const u16 = (b: Uint8Array): string => new TextDecoder('utf-16le').decode(b).replace(/\0+$/, '');

test('wrapper .fst parses with tools/flp and round-trips byte-exact', () => {
  const fst = buildWrapperFst({ plugclass: 0, displayName: 'OTT', filename: 'C:\\VST2\\OTT_x64.dll', vendor: 'Xfer Records', magic: 0x58665454 });
  const f = parseFlp(fst);
  assert.equal(firstDiff(fst, writeFlp(f)), -1);
  assert.deepEqual([f.header.format, f.header.nChannels, f.header.ppq, f.header.hdrExtra.length], [0x30, 2, 48, 0]);
  assert.equal(f.dtSlack.length, 0);
  assert.equal(f.trailer.length, 0);
  assert.deepEqual(f.events.map((e) => e.id), [199, 28, 201, 212, 203, 213]);
  assert.equal(new TextDecoder().decode(f.events[0].data), '11.5.5\0');
  assert.deepEqual([...f.events[1].data], [1]);
  assert.equal(u16(f.events[2].data), 'Fruity Wrapper');
  assert.equal(f.events[3].data.length, 52);
  assert.equal(u16(f.events[4].data), 'OTT');
});

test('chunk is accepted by the flp wrapper-data parser: kind 8, records 2,50,51,54,55,56', () => {
  const c = buildWrapperChunk({ plugclass: 0, displayName: 'OTT', filename: 'C:\\VST2\\OTT_x64.dll', vendor: 'Xfer Records', magic: 0x58665454 });
  const v = parseWrapperData(c)!;
  assert.equal(v.version, 8);
  assert.equal(v.fourcc, 'TTfX'); // raw LE u32 bytes of uniqueID 'XfTT'
  assert.equal(v.name, 'OTT_x64');
  assert.equal(v.path, 'C:\\VST2\\OTT_x64.dll');
  assert.equal(v.vendor, 'Xfer Records');
  const dv = new DataView(c.buffer, c.byteOffset);
  const ids: number[] = [];
  for (let p = 4; p + 12 <= c.length; p += 12 + Number(dv.getBigUint64(p + 4, true))) ids.push(dv.getUint32(p, true));
  assert.deepEqual(ids, [2, 50, 51, 54, 55, 56]);
});

test('record layout per class: VST3 → 52 (guid), CLAP → 58 (id string), generator header flag', () => {
  const cid = tuidFromHex('56534558667350736572756D20320000');
  const c3 = buildWrapperChunk({ plugclass: 8, displayName: 'Serum 2', filename: 'C:\\VST3\\Serum2.vst3', guid: cid, vendor: 'Xfer Records' });
  const dv = new DataView(c3.buffer, c3.byteOffset);
  const recs: Array<[number, number]> = [];
  for (let p = 4; p + 12 <= c3.length; p += 12 + Number(dv.getBigUint64(p + 4, true))) recs.push([dv.getUint32(p, true), Number(dv.getBigUint64(p + 4, true))]);
  assert.deepEqual(recs, [[2, 25], [50, 16], [52, 16], [54, 'Serum2'.length], [55, 'C:\\VST3\\Serum2.vst3'.length], [56, 12]]);
  assert.equal(dv.getUint32(4 + 12 + 25 + 12, true), 8); // record 50 payload = plugclass
  const clap = buildWrapperChunk({ plugclass: 12, displayName: 'Surge', filename: 'C:\\CLAP\\s.clap', idstring: 'org.surge' });
  assert.equal(parseWrapperData(clap)!.name, 'Surge'); // CLAP: name record = display name
  const g = parseFlp(buildWrapperFst({ plugclass: 8, displayName: 'Serum 2', filename: 'x.vst3', guid: cid }));
  assert.equal(new DataView(g.events[3].data.buffer, g.events[3].data.byteOffset).getUint16(16, true), 0x10);
});

test('record 2 flag bits follow bitness availability', () => {
  const flags = (has32: boolean, has64: boolean): number => {
    const c = buildWrapperChunk({ plugclass: 0, displayName: 'x', filename: 'x.dll', has32, has64 });
    return new DataView(c.buffer, c.byteOffset).getUint32(4 + 12 + 9, true);
  };
  assert.equal(flags(false, true), 0x507d08);
  assert.equal(flags(true, false), 0x507908);
  assert.equal(flags(true, true), 0x407908);
});

test('structure matches the FL-written shipped plugin-state files (FL 11.5.5: fmt 0x30, 2ch, ppq 48, 199/28/201/212/…/213)', { skip: !HAVE_FL }, () => {
  const dir = `${FL_ROOT}/Data/System/Plugin databases`;
  let n = 0;
  for (const p of filesWithExt(dir, '.fst')) {
    const f = parseFlp(read(p));
    const v = new TextDecoder().decode(f.events[0].data);
    if (v !== '11.5.5\0') continue;
    n++;
    assert.deepEqual([f.header.format, f.header.nChannels, f.header.ppq], [0x30, 2, 48]);
    assert.deepEqual(f.events.map((e) => e.id).slice(0, 4), [199, 28, 201, 212]);
    assert.equal(f.events[3].data.length, 52);
    assert.equal(f.events.at(-1)!.id, 213);
  }
  assert.ok(n >= 20, `11.5.5 files: ${n}`);
});

test('assembleFst reproduces FL-written 11.5.5 plugin-state files byte-exactly (container writer vs shipped files)', { skip: !HAVE_FL }, () => {
  const dir = `${FL_ROOT}/Data/System/Plugin databases`;
  let n = 0;
  for (const p of filesWithExt(dir, '.fst')) {
    const raw = read(p);
    const f = parseFlp(raw);
    if (new TextDecoder().decode(f.events[0].data) !== '11.5.5\0') continue;
    const again = assembleFst(f.events.map((e) => ({ id: e.id, data: e.data })), { format: f.header.format, nChannels: f.header.nChannels, ppq: f.header.ppq });
    assert.equal(firstDiff(raw, again), -1, p);
    n++;
  }
  assert.ok(n >= 20, `reproduced ${n}`);
});
