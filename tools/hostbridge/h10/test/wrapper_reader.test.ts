import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFlp } from '../../../flp/src/flp.ts';
import { parseWrapperData } from '../../../flp/src/summary.ts';
import { buildWrapperChunk } from '../../nfo/src/fst.ts';
import { generateDb, type PluginSpec } from '../../nfo/src/generate.ts';
import { MAX_VERSION, KNOWN_IDS, readWrapperChunk, interpretRecord2, hostQuery } from '../src/wrapper_reader.ts';

const here = dirname(fileURLToPath(import.meta.url));
const NFO = join(here, '..', '..', 'nfo');
const hex = (b: Uint8Array): string => Buffer.from(b).toString('hex').toUpperCase();

function chunkOf(fst: Uint8Array): Uint8Array {
  const f = parseFlp(fst);
  const ev = f.events.find((e) => e.id === 213);
  assert.ok(ev, 'event 213');
  return ev.data;
}

const specs: PluginSpec[] = JSON.parse(readFileSync(join(NFO, 'specs', 'wasm_plugins.json'), 'utf8')).plugins;
const generated = generateDb(specs);
const realOtt = readFileSync(join(NFO, 'evidence', 'real_machine', 'OTT.fst'));

/** rebuild a chunk from a record list (id, payload) with a given version, as FL's writer would lay it out */
function build(version: number, recs: Array<[number, Uint8Array]>): Uint8Array {
  const parts: number[] = [];
  const u32 = (v: number): void => { parts.push(v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255); };
  u32(version);
  for (const [id, p] of recs) {
    u32(id); u32(p.length); u32(0);
    parts.push(...p);
  }
  return Uint8Array.from(parts);
}
function records(chunk: Uint8Array): Array<[number, Uint8Array]> {
  const dv = new DataView(chunk.buffer, chunk.byteOffset, chunk.byteLength);
  const out: Array<[number, Uint8Array]> = [];
  for (let p = 4; p + 12 <= chunk.length;) {
    const id = dv.getUint32(p, true), n = Number(dv.getBigUint64(p + 4, true));
    out.push([id, chunk.slice(p + 12, p + 12 + n)]);
    p += 12 + n;
  }
  return out;
}

test('real-machine OTT.fst (VST3, 323 B): accepted; records [2,50,52,54,55,56]; CID/class/name/path/vendor read back', () => {
  const r = readWrapperChunk(chunkOf(realOtt));
  assert.equal(r.status, 'ok');
  assert.equal(r.version, 8);
  assert.equal(r.stringEncoding, 'ansi');
  assert.deepEqual(r.records.map((x) => x.id), [2, 50, 52, 54, 55, 56]);
  assert.ok(r.records.every((x) => x.known));
  assert.equal(r.consumedAll, true);
  assert.equal(r.fields.plugclass, 7);
  assert.equal(hex(r.fields.cid), '5854535654666F547474000000000000');
  assert.equal(r.fields.name, 'OTT');
  assert.equal(r.fields.path, 'C:\\Program Files\\Common Files\\VST3\\OTT.vst3');
  assert.equal(r.fields.vendor, 'Xfer Records');
  // absent records fall back to defaults
  assert.equal(r.fields.vstVersion, 1);
  assert.equal(r.fields.midi, undefined);
  assert.equal(r.fields.inputs.length + r.fields.outputs.length, 0);
  assert.equal(r.fields.state, undefined);
  const f2 = interpretRecord2(r.fields.record2);
  assert.deepEqual([f2.flags, f2.useDefaultOptions, f2.only64, f2.singleArch, f2.bitnessMismatch], [0x507d08, true, true, true, false]);
  assert.equal(interpretRecord2(r.fields.record2, false).bitnessMismatch, true); // same chunk on a 32-bit host would need the other bitness
});

test('generated DB (wasm_plugins.json, 5 entries): every .fst chunk is accepted with only known ids and identity records', () => {
  let n = 0;
  for (const e of generated.entries) {
    const c = chunkOf(generated.files.get(e.fst)!);
    const r = readWrapperChunk(c);
    assert.equal(r.status, 'ok', e.spec.name);
    assert.equal(r.version, 8);
    assert.ok(r.records.every((x) => x.known), `${e.spec.name}: unknown ids ${r.records.filter((x) => !x.known).map((x) => x.id)}`);
    assert.equal(r.consumedAll, true);
    const ids = r.records.map((x) => x.id);
    for (const absent of [0x01, 0x1e, 0x1f, 0x20, 0x35, 0x39]) assert.ok(!ids.includes(absent), `${e.spec.name}: record ${absent} unexpectedly present`);
    if (e.spec.format === 'vst2') { assert.ok(ids.includes(0x33)); assert.notEqual(r.fields.magic, 0); } else { assert.ok(ids.includes(0x34)); assert.ok(r.fields.cid.some((b) => b)); }
    assert.equal(r.fields.name !== undefined && r.fields.path !== undefined, true);
    assert.equal(r.fields.plugclassPresent, true);
    assert.equal(interpretRecord2(r.fields.record2).bitnessMismatch, false);
    n++;
  }
  assert.equal(n, 5);
});

test('host query (msg 7) for the generated OTT VST2 / Serum 2 VST3 entries carries class + name + vstid|guid', () => {
  const byName = (name: string) => readWrapperChunk(chunkOf(generated.files.get(generated.entries.find((e) => e.spec.name === name)!.fst)!));
  assert.equal(hostQuery(byName('OTT').fields), 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll|class=0|name=OTT_x64|vstid=1483101268');
  const s2 = hostQuery(byName('Serum 2').fields);
  assert.match(s2, /\|class=8\|name=Serum2\|guid=\{56534558-6673-5073-6572-756D20320000\}$/);
});

test('record 57 is effGetVstVersion (default 1), not an entry-point hint; reader never reads a hint from any record', () => {
  const base = records(chunkOf(generated.files.get(generated.entries.find((e) => e.spec.name === 'OTT')!.fst)!));
  const v = new Uint8Array(4);
  new DataView(v.buffer).setUint32(0, 2400, true);
  const r = readWrapperChunk(build(8, [...base, [0x39, v]]));
  assert.equal(r.fields.vstVersion, 2400);
  assert.equal(r.status, 'ok');
  assert.equal(hostQuery(r.fields), 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll|class=0|name=OTT_x64|vstid=1483101268'); // 57 does not change the lookup
  assert.deepEqual([...KNOWN_IDS], [1, 2, 30, 31, 32, 50, 51, 52, 53, 54, 55, 56, 57, 58]);
});

test('NEGATIVE: version gate — 13 rejected, -1 ignored, 4 → legacy reader, 5..12 → record reader (max = writer 12)', () => {
  const base = records(chunkOf(realOtt));
  assert.equal(MAX_VERSION, 12);
  assert.equal(readWrapperChunk(build(13, base)).status, 'rejected-newer-version');
  assert.equal(readWrapperChunk(build(13, base)).records.length, 0);
  assert.equal(readWrapperChunk(build(-1 >>> 0, base)).status, 'ignored-minus1');
  assert.equal(readWrapperChunk(build(4, base)).status, 'legacy-reader');
  for (const v of [5, 6, 7, 8, 9, 10, 11, 12]) assert.equal(readWrapperChunk(build(v, base)).status, 'ok', `v${v}`);
  // the leading u32 is a format version (a VST3 .fst carries 8), and tools/flp must agree with the Wrapper reader
  assert.equal(parseWrapperData(chunkOf(realOtt))!.version, 8);
  assert.equal(parseWrapperData(chunkOf(realOtt))!.plugclass, 7);
  assert.equal(readWrapperChunk(chunkOf(realOtt)).fields.plugclass, 7);
});

test('NEGATIVE: record 50 absent → class defaults to 0 (VST2 fx) — a VST3 chunk is misrouted, not rejected', () => {
  const base = records(chunkOf(realOtt)).filter(([id]) => id !== 50);
  const r = readWrapperChunk(build(8, base));
  assert.equal(r.status, 'ok');
  assert.equal(r.fields.plugclass, 0);
  assert.equal(r.fields.plugclassPresent, false);
  assert.match(hostQuery(r.fields), /\|class=0\|name=OTT\|guid=/);
});

test('NEGATIVE: unknown ids are skipped; ids 31/32 of any size and a missing 53 are harmless', () => {
  const base = records(chunkOf(realOtt));
  const junk = Uint8Array.from([1, 2, 3, 4, 5]);
  const r = readWrapperChunk(build(8, [[99, junk], ...base, [0x1f, new Uint8Array(30)], [0x2b, junk]]));
  assert.equal(r.status, 'ok');
  assert.deepEqual(r.records.filter((x) => !x.known).map((x) => x.id), [99, 0x2b]);
  assert.equal(r.fields.name, 'OTT');
  assert.equal(r.fields.inputs.length, 24); // floor(30/12)*12 bytes are used (2 entries)
});

test('NEGATIVE: string encoding follows the version (<=8 ANSI, >=9 UTF-8); path "/" is normalized to "\\"', () => {
  const nameBytes = Uint8Array.from([0xc3, 0xa9]); // "é" in UTF-8
  const recs: Array<[number, Uint8Array]> = [[50, new Uint8Array(16)], [54, nameBytes], [55, new TextEncoder().encode('C:/VST2/x.dll')]];
  assert.equal(readWrapperChunk(build(8, recs)).fields.name, 'Ã©');
  assert.equal(readWrapperChunk(build(9, recs)).fields.name, 'é');
  assert.equal(readWrapperChunk(build(8, recs)).fields.path, 'C:\\VST2\\x.dll');
});

test('NEGATIVE: truncated chunk — loop ends without throwing, consumedAll=false, partial strings kept', () => {
  const c = chunkOf(generated.files.get(generated.entries.find((e) => e.spec.name === 'OTT')!.fst)!);
  const r = readWrapperChunk(c.subarray(0, c.length - 3));
  assert.equal(r.status, 'ok');
  assert.equal(r.consumedAll, false);
  assert.equal(r.fields.vendor, 'Xfer Records'.slice(0, 'Xfer Records'.length - 3));
});

test('the generator output is byte-identical to buildWrapperChunk for the OTT spec (same chunk the model read)', () => {
  const e = generated.entries.find((x) => x.spec.name === 'OTT')!;
  const direct = buildWrapperChunk({ plugclass: 0, displayName: 'OTT', filename: 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll', vendor: 'Xfer Records', magic: 0x58665454, has32: false, has64: true });
  assert.equal(hex(chunkOf(generated.files.get(e.fst)!)), hex(direct));
});
