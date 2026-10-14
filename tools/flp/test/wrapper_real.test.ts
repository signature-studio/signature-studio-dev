// Real-data checks for the Fruity Wrapper chunk (event 213). #110 (L-7).
// - repo fixture: real-machine OTT.fst (VST3, version 8), always run.
// - FL corpus: Fruity Mute 2.flp / Fruity Phase Inverter.flp (both wrapper-hosted), run when WRAPPER_FLP_DIR points at a dir holding them.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFlp } from '../src/flp.ts';
import { parseWrapperChunk, writeWrapperChunk, parseWrapperData } from '../src/summary.ts';

const here = dirname(fileURLToPath(import.meta.url));
const ottFst = join(here, '..', '..', 'hostbridge', 'nfo', 'evidence', 'real_machine', 'OTT.fst');
const hex = (b: Uint8Array): string => Buffer.from(b).toString('hex');

function chunksOf(file: Uint8Array): Uint8Array[] {
  return parseFlp(file).events.filter((e) => e.id === 213).map((e) => e.data);
}

test('real-machine OTT.fst: chunk parses, write-back is byte-exact, fields as the Wrapper reads them', () => {
  const c = chunksOf(readFileSync(ottFst))[0];
  const w = parseWrapperChunk(c);
  assert.ok(w, 'accepted');
  assert.equal(w.version, 8);
  assert.deepEqual(w.records.map((r) => r.id), [2, 50, 52, 54, 55, 56]);
  assert.equal(hex(writeWrapperChunk(w)), hex(c));
  const v = parseWrapperData(c)!;
  assert.equal(v.plugclass, 7);
  assert.equal(v.name, 'OTT');
  assert.equal(v.vendor, 'Xfer Records');
  assert.equal(v.path, 'C:\\Program Files\\Common Files\\VST3\\OTT.vst3');
  assert.equal(v.vstVersion, 1);
});

test('NEGATIVE: wrong version / truncation / trailing garbage are rejected; a broken write-back is detected', () => {
  const c = chunksOf(readFileSync(ottFst))[0];
  const bad13 = Uint8Array.from(c); bad13[0] = 13;
  assert.equal(parseWrapperChunk(bad13), undefined);
  assert.equal(parseWrapperChunk(c.subarray(0, c.length - 1)), undefined);
  assert.equal(parseWrapperChunk(Uint8Array.from([...c, 0])), undefined);
  // a writer that dropped record 50 would not reproduce the chunk: the round-trip check must notice
  const w = parseWrapperChunk(c)!;
  const dropped = writeWrapperChunk({ ...w, records: w.records.filter((r) => r.id !== 50) });
  assert.notEqual(hex(dropped), hex(c));
});

const flpDir = process.env.WRAPPER_FLP_DIR;
const corpus = ['Fruity Mute 2.flp', 'Fruity Phase Inverter.flp'];

for (const name of corpus) {
  test(`FL corpus ${name}: wrapper chunk round-trips byte-exactly; the native 213 is rejected`, { skip: !flpDir || !existsSync(join(flpDir!, name)) }, () => {
    const chunks = chunksOf(readFileSync(join(flpDir!, name)));
    const accepted = chunks.map((c) => ({ c, w: parseWrapperChunk(c) })).filter((x) => x.w);
    assert.equal(accepted.length, 1, `wrapper chunks in ${name}`);
    const { c, w } = accepted[0]!;
    assert.equal(hex(writeWrapperChunk(w!)), hex(c));
    assert.equal(w!.version, 8);
    const v = parseWrapperData(c)!;
    assert.equal(v.name, name.replace(/\.flp$/, ''));
    assert.match(v.path ?? '', /\\Plugins\\VST\\.*\.dll$/);
    // the other 213 in the project is a native plugin state, not a wrapper record list
    assert.equal(chunks.length - accepted.length, 1);
  });
}
