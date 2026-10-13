// #549 [HB-H14]: non-ASCII names/paths in the wrapper chunk — version 8 (ANSI = CP_ACP) vs 9..12 (UTF-8).
// The shimx side is measured, not assumed: work/shimx_acp_probe.cjs is built by h10_e2e.sh (analysis/shimx_acp_probe.c, the
// real src/str.c MultiByteToWideChar) and run here; its UTF-16 result is compared with the reader model's decode of the same bytes.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFlp } from '../../../flp/src/flp.ts';
import { buildWrapperChunk, buildWrapperFst } from '../../nfo/src/fst.ts';
import { generateDb, type PluginSpec } from '../../nfo/src/generate.ts';
import { readWrapperChunk, hostQuery, type AnsiCodePage } from '../src/wrapper_reader.ts';

const here = dirname(fileURLToPath(import.meta.url));
const PROBE = join(here, '..', 'work', 'shimx_acp_probe.cjs');

const hexBytes = (h: string): Uint8Array => Uint8Array.from(Buffer.from(h, 'hex'));

/** wrapper chunk (header = 12 B {u32 id, u64 size}) from records, the layout fst.ts / FL write */
function build(version: number, recs: Array<[number, Uint8Array]>): Uint8Array {
  const parts: number[] = [];
  const u32 = (v: number): void => { parts.push(v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255); };
  u32(version);
  for (const [id, p] of recs) { u32(id); u32(p.length); u32(0); parts.push(...p); }
  return Uint8Array.from(parts);
}

/** ANSI bytes of the test strings. Expected values come from Python's stdlib codecs (independent of shimx's tables):
 *  python3 -c "print('…'.encode('cp932').hex())" / .encode('cp1252') */
const V = {
  jpPath: { text: 'C:\\Users\\日本太郎\\VST\\OTT.dll', cp932: '433a5c55736572735c93fa967b91be98595c5653545c4f54542e646c6c' },
  jpName: { text: '日本語プラグイン', cp932: '93fa967b8cea83768389834f83438393' },
  katakana: { text: 'ユーザ', cp932: '8386815b8355' },
  halfwidth: { text: 'ｱｲｳ', cp932: 'b1b2b3' },
  /** 0x5C ('\') as the trail byte of 表 (95 5C): the reader must not treat it as a path separator before decoding */
  trail5c: { text: 'C:\\表\\a.dll', cp932: '433a5c955c5c612e646c6c' },
  latin: { text: 'Café', cp1252: '436166e9' },
} as const;

function probe(acp: number, hexes: string[]): Array<{ acp: number; hex: string; utf16?: string; err?: number }> {
  assert.ok(existsSync(PROBE), `${PROBE} missing — build it first: bash tools/hostbridge/h10/h10_e2e.sh (emcc step)`);
  const out = execFileSync('node', [PROBE, String(acp), ...hexes], { encoding: 'utf8' }).trim().split('\n');
  assert.match(out[0], /^GETACP \d+$/);
  return out.slice(1).map((l) => {
    const [a, hex, res] = l.split(' ');
    return res.startsWith('ERR:') ? { acp: Number(a), hex, err: Number(res.slice(4)) } : { acp: Number(a), hex, utf16: Buffer.from(res, 'hex').toString('utf16le') };
  });
}

test('shimx CP_ACP default = 1252 (GetACP; no shimx_set_acp) and 932 only after shimx_set_acp(932)', () => {
  const d = execFileSync('node', [PROBE, '0'], { encoding: 'utf8' }).trim();
  assert.equal(d, 'GETACP 1252');
  assert.equal(execFileSync('node', [PROBE, '932'], { encoding: 'utf8' }).trim(), 'GETACP 932');
});

test('shimx MultiByteToWideChar(CP_ACP) == reader-model decode, for ACP 1252 (default) and 932, on every vector', () => {
  const all = [V.jpPath.cp932, V.jpName.cp932, V.katakana.cp932, V.halfwidth.cp932, V.trail5c.cp932, V.latin.cp1252];
  let n = 0;
  for (const [acp, model] of [[0, 'windows-1252'], [932, 'shift_jis']] as Array<[number, AnsiCodePage]>) {
    for (const r of probe(acp, all)) {
      const m = readWrapperChunk(build(8, [[50, new Uint8Array(16)], [54, hexBytes(r.hex)]]), model).fields.name!;
      if (r.err !== undefined) assert.ok(m.includes('\ufffd'), `${model} ${r.hex}: shimx ERR ${r.err} but model decoded ${JSON.stringify(m)}`);
      else assert.equal(r.utf16, m, `${model} ${r.hex}`);
      n++;
    }
  }
  assert.equal(n, 12);
});

test('version 8 + CP932 bytes: correct under ACP 932, mojibake under the shimx default 1252 (the issue)', () => {
  for (const v of [V.jpPath, V.jpName, V.katakana, V.halfwidth, V.trail5c]) {
    const chunk = build(8, [[50, new Uint8Array(16)], [54, hexBytes(v.cp932)], [55, hexBytes(v.cp932)]]);
    const at932 = readWrapperChunk(chunk, 'shift_jis');
    assert.equal(at932.stringEncoding, 'ansi');
    assert.equal(at932.fields.name, v.text);
    assert.equal(at932.fields.path, v.text.replace(/\//g, '\\'));
    assert.notEqual(readWrapperChunk(chunk).fields.name, v.text, `1252 must NOT reproduce ${v.text} (negative control)`);
  }
  // …and the probe agrees that the default shimx does not reproduce it
  assert.notEqual(probe(0, [V.jpName.cp932])[0].utf16, V.jpName.text);
  assert.equal(probe(932, [V.jpName.cp932])[0].utf16, V.jpName.text);
});

test('version 8 generator: ASCII only — non-ASCII name/path/vendor/clap id throws (no silent code-page dependence)', () => {
  const base = { plugclass: 0, displayName: 'OTT', filename: 'C:\\VST2\\OTT_x64.dll', vendor: 'Xfer', magic: 0x58665454 };
  assert.doesNotThrow(() => buildWrapperChunk(base));
  assert.throws(() => buildWrapperChunk({ ...base, filename: V.jpPath.text }), /record 54|record 55/);
  assert.throws(() => buildWrapperChunk({ ...base, filename: 'C:\\VST2\\a.dll', nameRecord: V.jpName.text }), /record 54 \(name\).*non-ASCII/);
  assert.throws(() => buildWrapperChunk({ ...base, vendor: V.latin.text }), /record 56 \(vendor\).*non-ASCII/);
  assert.throws(() => buildWrapperChunk({ plugclass: 11, displayName: 'x', filename: '', idstring: 'com.例.x' }), /record 58 \(CLAP id\).*non-ASCII/);
  assert.throws(() => buildWrapperChunk({ ...base, version: 8, filename: V.jpPath.text }), /non-ASCII/);
});

test('version 9..12 generator: UTF-8 strings round-trip through the reader under ANY CP_ACP (1252 and 932)', () => {
  for (const version of [9, 10, 11, 12]) {
    const spec = { plugclass: 7, displayName: V.jpName.text, filename: V.jpPath.text.replace('OTT.dll', 'プラグイン.vst3'), nameRecord: V.jpName.text, vendor: V.katakana.text, guid: new Uint8Array(16).fill(7), version };
    const chunk = buildWrapperChunk(spec);
    assert.equal(new DataView(chunk.buffer, chunk.byteOffset).getUint32(0, true), version);
    for (const acp of ['windows-1252', 'shift_jis'] as AnsiCodePage[]) {
      const r = readWrapperChunk(chunk, acp);
      assert.equal(r.status, 'ok');
      assert.equal(r.stringEncoding, 'utf8');
      assert.equal(r.consumedAll, true);
      assert.deepEqual([r.fields.name, r.fields.path, r.fields.vendor], [V.jpName.text, spec.filename, V.katakana.text], `v${version} ${acp}`);
    }
    assert.match(hostQuery(readWrapperChunk(chunk).fields), /^C:\\Users\\日本太郎\\VST\\プラグイン\.vst3\|class=7\|name=日本語プラグイン\|guid=/);
  }
  // NEGATIVE: the same UTF-8 bytes under version 8 are read as ANSI → mojibake (why version 8 may not carry them)
  const chunk9 = buildWrapperChunk({ plugclass: 0, displayName: 'x', filename: '', nameRecord: V.jpName.text, magic: 1, version: 9 });
  const as8 = Uint8Array.from(chunk9); as8[0] = 8;
  for (const acp of ['windows-1252', 'shift_jis'] as AnsiCodePage[]) assert.notEqual(readWrapperChunk(as8, acp).fields.name, V.jpName.text, acp);
});

test('generator rejects versions outside 8..12 (Wrapper accepts 5..12; < 8 is not what FL writes, > 12 is rejected by the Wrapper)', () => {
  const base = { plugclass: 0, displayName: 'x', filename: 'C:\\a.dll', magic: 1 };
  for (const version of [7, 13, 8.5, -1]) assert.throws(() => buildWrapperChunk({ ...base, version }), /generator supports 8\.\.12/);
  for (const version of [8, 9, 12]) assert.equal(readWrapperChunk(buildWrapperChunk({ ...base, version })).status, 'ok');
});

test('generateDb: default (v8) throws on a Japanese plugin path; chunkVersion 9 writes .fst whose chunk reads back (end to end through .fst parse)', () => {
  const spec: PluginSpec = { name: '日本語プラグイン', vendor: 'ユーザ', format: 'vst3', kind: 'effect', path: V.jpPath.text.replace('OTT.dll', 'プラグイン.vst3'), guid: '56534558667350737275006d32000000' };
  assert.throws(() => generateDb([spec]), /non-ASCII/);
  const res = generateDb([spec], { chunkVersion: 9 });
  const fst = res.files.get(res.entries[0].fst)!;
  const ev = parseFlp(fst).events.find((e) => e.id === 213)!;
  const r = readWrapperChunk(ev.data, 'windows-1252');
  assert.equal(r.version, 9);
  assert.equal(r.stringEncoding, 'utf8');
  assert.equal(r.fields.path, spec.path);
  assert.equal(r.fields.vendor, spec.vendor);
  assert.equal(r.fields.name, 'プラグイン');
  // the default (version 8) output for an ASCII spec: u32 8, and the string payloads of records 54/55/56 are pure 7-bit
  const ascii = buildWrapperFst({ plugclass: 0, displayName: 'OTT', filename: 'C:\\VST2\\OTT_x64.dll', vendor: 'Xfer Records', magic: 0x58665454 });
  const c8 = parseFlp(ascii).events.find((e) => e.id === 213)!.data;
  assert.equal(c8[0], 8);
  const r8 = readWrapperChunk(c8);
  const strRecs = r8.records.filter((x) => [0x36, 0x37, 0x38].includes(x.id));
  assert.equal(strRecs.length, 3);
  for (const x of strRecs) assert.ok(c8.subarray(x.offset, x.offset + x.size).every((b) => b < 0x80), `record ${x.id} is 7-bit`);
  assert.equal(readWrapperChunk(c8, 'shift_jis').fields.path, readWrapperChunk(c8, 'windows-1252').fields.path); // ASCII: CP_ACP-independent
});
