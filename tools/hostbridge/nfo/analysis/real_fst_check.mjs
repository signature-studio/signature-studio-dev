// CAB-215 (H9a, partial): validate the real-machine OTT.fst sample against the CAB-98 toolchain.
//
//   node analysis/real_fst_check.mjs
//
// Sample: evidence/real_machine/OTT.fst (323 B, copied from a user Windows machine,
// `%USERPROFILE%\Documents\Image-Line\FL Studio\Presets\Plugin database\Installed\Effects\VST3\OTT.fst`).
// The machine had NO OTT.nfo / VerifiedIDs.nfo / .Plugins.ini — the .fst alone was present.
//
// Checks (exit 1 when any fails):
//   1. CAB-98 container writer (assembleFst) reproduces the file byte-exactly from parsed events.
//   2. tools/flp independent parser: parseFlp lossless round-trip (firstDiff === -1) + parseWrapperData accepts chunk 213.
//   3. Full event dump + full wrapper-chunk record dump (incl. VST3 CID extraction).
//   4. buildWrapperFst (CAB-98 generator) reproduces the file byte-exactly from the spec extracted out of the sample.
//   5. generateDb with a hypothetical OTT VST3 spec (CID + real path) → byte-identical .fst; its .nfo passes the
//      CAB-98 reader model (entryFromBytes: accepted, no rejected files).
//   6. Diff table vs the current specs/wasm_plugins.json OTT entry (VST2).
// Output: evidence/real_machine/ott_fst_dump.json (also printed summary to stdout).
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { FL_MAC_DIR } from '../../../shared/paths.mjs';
import { parseFlp, writeFlp, firstDiff, kindOf } from '../../../flp/src/flp.ts';
import { parseWrapperData } from '../../../flp/src/summary.ts';
import { assembleFst, buildWrapperFst } from '../src/fst.ts';
import { entryFromBytes, newFile } from '../src/entry.ts';
import { generateDb, DEFAULT_DB_PATH } from '../src/generate.ts';
import { guidToString, tuidFromHex, slotOf, familyOf, PlugClass } from '../src/format.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const NFO_DIR = join(HERE, '..');
const SAMPLE = join(NFO_DIR, 'evidence/real_machine/OTT.fst');
const OUT_JSON = join(NFO_DIR, 'evidence/real_machine/ott_fst_dump.json');

const sha256hex = (buf) => createHash('sha256').update(buf).digest('hex');

const fail = [];
const ok = (cond, label) => { console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${label}`); if (!cond) fail.push(label); return cond; };

// ---------- generic wrapper-chunk record walk (FORMAT.md §8; independent of parseWrapperData) ----------
function walkWrapperRecords(d) {
  const dv = new DataView(d.buffer, d.byteOffset, d.byteLength);
  const version = dv.getUint32(0, true);
  const records = [];
  let p = 4;
  while (p + 12 <= d.length) {
    const id = dv.getUint32(p, true);
    const size = Number(dv.getBigUint64(p + 4, true));
    p += 12;
    if (p + size > d.length) return { version, records, overrun: true };
    records.push({ id, size, off: p, bytes: d.slice(p, p + size) });
    p += size;
  }
  return { version, records, overrun: false, consumed: p };
}

const ascii = (b) => new TextDecoder('utf-8').decode(b);
const hex = (b) => [...b].map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase();
const utf16z = (b) => new TextDecoder('utf-16le').decode(b).replace(/\0+$/, '');
const asciiz = (b) => ascii(b).replace(/\0+$/, '');
const CLASS_NAMES = { 0: 'VST fx', 1: 'DX fx', 2: 'FL fx', 3: 'FL gen', 4: 'VST gen', 5: 'DX gen', 7: 'VST3 fx', 8: 'VST3 gen', 9: 'AU fx', 10: 'AU gen', 11: 'CLAP fx', 12: 'CLAP gen' };

function decodeRecord(r) {
  const b = r.bytes, dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  switch (r.id) {
    case 2: {
      const flags = dv.getUint32(9, true);
      return {
        kind: 'wrapper flags', u8_0: b[0], i32_1: dv.getInt32(1, true), i32_5: dv.getInt32(5, true),
        flags, flagsHex: '0x' + flags.toString(16).toUpperCase(),
        flagsModel: { base: '0x407908', delta64only: '0x400', deltaNotBoth: '0x100000' },
        u32_13: dv.getUint32(13, true), u8_17: b[17],
      };
    }
    case 50: return { kind: 'plugclass', value: dv.getUint32(0, true), name: CLASS_NAMES[dv.getUint32(0, true)] };
    case 51: return { kind: 'VST2 uniqueID', u32: dv.getUint32(0, true), fourcc: ascii(b) };
    case 52: return { kind: 'VST3 class id (CID)', hex: hex(b), ascii: asciiZ(b), guidText: guidToString(b) };
    case 54: return { kind: 'name (file basename / CLAP id)', text: ascii(b) };
    case 55: return { kind: 'plugin path', text: ascii(b) };
    case 56: return { kind: 'vendor', text: ascii(b) };
    case 58: return { kind: 'CLAP id', text: ascii(b) };
    case 53: return { kind: 'plugin state', size: b.length, sha256: sha256hex(b) };
    default: return { kind: 'unknown', hex: hex(b) };
  }
}
const asciiZ = (b) => { const z = b.indexOf(0); return ascii(z < 0 ? b : b.slice(0, z)); };

function decodeEvent(e) {
  const base = { id: e.id, kind: kindOf(e.id), off: e.off, len: e.data.length };
  switch (e.id) {
    case 199: return { ...base, text: asciiz(e.data), meaning: 'FlVersion' };
    case 28: return { ...base, value: e.data[0], meaning: 'byte flag (DB write path passes 1)' };
    case 201: return { ...base, text: utf16z(e.data), meaning: 'plugin internal name' };
    case 212: {
      const dv = new DataView(e.data.buffer, e.data.byteOffset, e.data.byteLength);
      return { ...base, u32_at8: dv.getUint32(8, true), u16_at16: dv.getUint16(16, true), hex: hex(e.data), meaning: 'wrapper header' };
    }
    case 203: return { ...base, text: utf16z(e.data), meaning: 'display name' };
    case 213: return { ...base, meaning: 'wrapper chunk', hex: hex(e.data) };
    default: return { ...base, hex: hex(e.data) };
  }
}

// ---------- load sample ----------
const buf = new Uint8Array(readFileSync(SAMPLE));
console.log(`sample: ${SAMPLE} (${buf.length} bytes, sha256 ${sha256hex(buf)})`);

const fl = parseFlp(buf);
const dump = {
  provenance: {
    source: 'user Windows machine (FL Studio 26.x), %USERPROFILE%\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST3\\OTT.fst',
    copiedBy: 'user', receivedAt: '2026-10-10', ticket: 'CAB-215 (partial)',
    note: 'OTT.nfo / VerifiedIDs.nfo / .Plugins.ini were NOT present on the machine (checked by user). VST3 folder registration.',
  },
  file: { size: buf.length, sha256: sha256hex(buf) },
  container: {
    flhd: { ...fl.header, hdrExtra: fl.header.hdrExtra.length ? hex(fl.header.hdrExtra) : undefined },
    dtLen: fl.dtLen, dtSlack: fl.dtSlack.length, trailer: fl.trailer.length, warnings: fl.warnings,
    events: fl.events.map(decodeEvent),
  },
};

// ---------- check 1: CAB-98 container writer round-trip ----------
console.log('[1] CAB-98 assembleFst container reconstruction (byte-exact)');
const rebuilt = assembleFst(fl.events.map((e) => ({ id: e.id, data: e.data })), { format: fl.header.format, nChannels: fl.header.nChannels, ppq: fl.header.ppq });
const c1 = firstDiff(buf, rebuilt) === -1;
ok(c1, `assembleFst(events) === original bytes (${rebuilt.length} B)`);
dump.checks = { assembleFstByteExact: c1 };

// ---------- check 2: tools/flp independent parser ----------
console.log('[2] tools/flp independent parser (parseFlp / writeFlp / parseWrapperData)');
const rewritten = writeFlp(fl);
const c2a = firstDiff(buf, rewritten) === -1;
ok(c2a, `parseFlp -> writeFlp lossless (firstDiff === -1)`);
const chunk213 = fl.events.find((e) => e.id === 213)?.data;
const w = chunk213 ? parseWrapperData(chunk213) : undefined;
const c2b = w !== undefined;
ok(c2b, `parseWrapperData(chunk 213) accepted: ${JSON.stringify(w ?? null)}`);
dump.checks.toolsFlp = { losslessRoundTrip: c2a, wrapperParsed: c2b, wrapper: w ? { kind: w.kind, fourcc: w.fourcc, guid: w.guid, name: w.name, path: w.path, vendor: w.vendor } : null };

// ---------- check 3: wrapper chunk records + CID ----------
console.log('[3] wrapper chunk 213 records (independent walk)');
const walk = chunk213 ? walkWrapperRecords(chunk213) : null;
const c3a = walk != null && walk.version === 8 && !walk.overrun && walk.consumed === chunk213.length;
ok(c3a, `u32 version = ${walk?.version}, ${walk?.records.length} records, chain consumes ${walk?.consumed}/${chunk213?.length} bytes`);
dump.wrapperChunk = {
  version: walk.version, length: chunk213.length, consumed: walk.consumed,
  records: walk.records.map((r) => ({ id: r.id, size: r.size, ...decodeRecord(r) })),
};
const rec = (id) => walk.records.find((r) => r.id === id);
const r50 = rec(50), r52 = rec(52), r54 = rec(54), r55 = rec(55), r56 = rec(56), r2 = rec(2);
const plugclass = r50 ? new DataView(r50.bytes.buffer, r50.bytes.byteOffset).getUint32(0, true) : -1;
const cidBytes = r52?.bytes;
const cid = cidBytes ? { hex: hex(cidBytes), ascii: asciiZ(cidBytes), guidText: guidToString(cidBytes), tuidHex: hex(tuidFromHex(hex(cidBytes))) } : null;
dump.vst3cid = cid;
console.log(`    CID: ${cid?.hex} (ascii "${cid?.ascii}", GUID text ${cid?.guidText})`);
ok(cid != null && cid.hex === cid.tuidHex, 'CID 16 B round-trips through tuidFromHex (raw TUID memory order)');

// ---------- check 4: buildWrapperFst byte-exact from sample-derived spec ----------
console.log('[4] CAB-98 buildWrapperFst from sample-derived spec (byte-exact)');
// has32/has64 are not in the .fst (they come from the .nfo, which this machine lacks); single 64-bit file is the
// natural assumption and is what the record-2 flags model predicts (0x400 | 0x100000 both set).
const specFromSample = {
  plugclass,
  displayName: utf16z(fl.events.find((e) => e.id === 203).data),
  filename: r55 ? ascii(r55.bytes) : '',
  nameRecord: r54 ? ascii(r54.bytes) : undefined,
  vendor: r56 ? ascii(r56.bytes) : undefined,
  guid: cidBytes,
  has32: false, has64: true,
};
const regen = buildWrapperFst(specFromSample);
const c4 = firstDiff(buf, regen) === -1;
ok(c4, `buildWrapperFst(sample spec) === real bytes (${regen.length} vs ${buf.length} B, firstDiff ${firstDiff(buf, regen)})`);
dump.checks.buildWrapperFstByteExact = c4;
dump.specFromSample = { ...specFromSample, guid: specFromSample.guid ? hex(specFromSample.guid) : undefined };

// ---------- check 5: generateDb hypothetical OTT VST3 entry + CAB-98 reader acceptance ----------
console.log('[5] generateDb (hypothetical OTT VST3 spec) + reader model acceptance');
const CID_HEX = cid.hex;
const hypSpec = {
  name: 'OTT', vendor: r56 ? ascii(r56.bytes) : 'Xfer Records', format: 'vst3', kind: 'effect',
  guid: CID_HEX, path: r55 ? ascii(r55.bytes) : 'C:\\Program Files\\Common Files\\VST3\\OTT.vst3',
};
const g = generateDb([hypSpec]);
const genFst = g.files.get('Installed/Effects/VST3/OTT.fst');
const genNfo = g.files.get('Installed/Effects/VST3/OTT.nfo');
const c5a = genFst != null && firstDiff(buf, genFst) === -1;
ok(c5a, `generateDb([...]).files["Installed/Effects/VST3/OTT.fst"] === real bytes (${genFst?.length} B, sha256 ${genFst ? sha256hex(genFst) : '-'})`);
const rd = entryFromBytes(genNfo, { dbPath: DEFAULT_DB_PATH });
const c5b = rd.dropped === undefined && rd.rejectedFiles.length === 0 && rd.entry?.files.length === 1;
ok(c5b, `reader model accepts the generated .nfo (dropped=${rd.dropped}, rejected=${JSON.stringify(rd.rejectedFiles)})`);
const gf = rd.entry?.files[0];
const c5c = gf != null && gf.plugclass === PlugClass.Vst3Fx && gf.bits === 3 && slotOf(gf.plugclass, gf.bits) === 5
  && guidToString(gf.guid) === cid.guidText && gf.filename === hypSpec.path;
ok(c5c, `reader model: plugclass=7 (VST3 fx), 64-bit, slot=5, ps_file_guid === CID as GUID text, filename = bundle folder path`);
dump.checks.generatedDbVst3 = { fstByteExact: c5a, readerAccepted: c5b, fields: c5c };
dump.hypotheticalVst3Entry = {
  note: 'NOT real data — what generateDb would write for an OTT VST3 entry (CID + path from the real .fst). For CAB-46/CAB-216/CAB-218 cross-check until a real .nfo arrives.',
  spec: hypSpec, fstPath: 'Installed/Effects/VST3/OTT.fst', fstSha256: sha256hex(genFst),
  nfoText: new TextDecoder().decode(genNfo),
  verifiedIdKey: `VST3:${cid.guidText}:64 -> Effects\\VST3\\OTT.NFO`,
  placement: `Installed\\Effects\\${familyOf(plugclass).toUpperCase()}\\ → real machine placed it in Installed\\Effects\\VST3\\ (matches)`,
};

// ---------- check 6: diff vs current specs/wasm_plugins.json OTT (VST2) ----------
console.log('[6] diff vs specs/wasm_plugins.json OTT entry (VST2)');
const specs = JSON.parse(readFileSync(join(NFO_DIR, 'specs/wasm_plugins.json'), 'utf8')).plugins;
const gCur = generateDb(specs);
const curFst = gCur.files.get('Installed/Effects/VST/OTT.fst');
const curFl = parseFlp(curFst);
const curChunk = walkWrapperRecords(curFl.events.find((e) => e.id === 213).data);
const realIds = walk.records.map((r) => r.id), curIds = curChunk.records.map((r) => r.id);
const diff = {
  placement: { real: 'Installed/Effects/VST3/OTT.fst (user machine)', generated: 'Installed/Effects/VST/OTT.fst (spec: format vst2)' },
  plugclass: { real: plugclass, generated: 0 },
  chunk213recordIds: { real: realIds, generated: curIds },
  record51_52: { real: r52 ? 'record 52 (CID ' + cid.hex + ' = "' + cid.ascii + '")' : '-', generated: 'record 51 (magic 0x58665454 "XfTT")' },
  record54: { real: r54 ? ascii(r54.bytes) : '-', generated: ascii(curChunk.records.find((r) => r.id === 54).bytes) },
  record55: { real: r55 ? ascii(r55.bytes) : '-', generated: ascii(curChunk.records.find((r) => r.id === 55).bytes) },
  record56vendor: { real: r56 ? ascii(r56.bytes) : '-', generated: ascii(curChunk.records.find((r) => r.id === 56).bytes) },
  event203: { real: utf16z(fl.events.find((e) => e.id === 203).data), generated: utf16z(curFl.events.find((e) => e.id === 203).data) },
  event212: { realU16at16: 0, genU16at16: (() => { const d = curFl.events.find((e) => e.id === 212).data; return new DataView(d.buffer, d.byteOffset, d.byteLength).getUint16(16, true); })() },
  container: 'FLhd / 199 "11.5.5" / 28=1 / 201 "Fruity Wrapper" identical',
  firstByteDiff: firstDiff(buf, curFst),
  sizes: { real: buf.length, generated: curFst.length },
};
dump.diffVsCurrentSpec = diff;
console.log(`    record ids real=${JSON.stringify(realIds)} vs generated=${JSON.stringify(curIds)}; first byte diff at ${diff.firstByteDiff}`);
ok(true, 'diff recorded (VST2 spec vs real VST3 registration — see REPORT appendix)');

// ---------- corpus contrast: record-2 flags in shipped 11.5.5 .fst (VST2-era writers) ----------
const FL_ROOT = process.env.FL_ROOT ?? `${FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL`;
const flagCounts = {};
if (existsSync(FL_ROOT)) {
  const walkFs = (dir) => readdirSync(dir).sort().flatMap((n) => {
    const p = join(dir, n), st = statSync(p);
    return st.isDirectory() ? walkFs(p) : (p.toLowerCase().endsWith('.fst') ? [p] : []);
  });
  for (const p of walkFs(FL_ROOT)) {
    try {
      const f = parseFlp(new Uint8Array(readFileSync(p)));
      const ch = f.events.find((e) => e.id === 213);
      if (!ch) continue;
      const wk = walkWrapperRecords(ch.data);
      if (wk.version !== 8 || wk.overrun || wk.consumed !== ch.data.length) continue; // native plugin states are not wrapper chunks
      const r2 = wk.records.find((r) => r.id === 2);
      if (!r2) continue;
      const flg = new DataView(r2.bytes.buffer, r2.bytes.byteOffset).getUint32(9, true);
      const key = '0x' + flg.toString(16).toUpperCase();
      flagCounts[key] = (flagCounts[key] ?? 0) + 1;
    } catch { /* not an fst we can parse */ }
  }
  const realFlags = r2 ? new DataView(r2.bytes.buffer).getUint32(9, true) : 0;
  dump.record2FlagsContrast = { realMachine: '0x' + realFlags.toString(16).toUpperCase(), shippedCorpusCounts: flagCounts, shippedWrapperChunkFst: Object.values(flagCounts).reduce((a, b) => a + b, 0), corpusRoot: FL_ROOT.startsWith(FL_MAC_DIR) ? `$FL_MAC_DIR${FL_ROOT.slice(FL_MAC_DIR.length)}` : FL_ROOT, note: 'shipped corpus has 0 wrapper-chunk .fst (REPORT §1) — this real file is the first observed record-2 flags value; 0x507D08 = 0x407908 | 0x400 | 0x100000 matches the fst.ts model for a 64-bit-only single-file entry' };
  console.log(`[+] record-2 flags: real=0x${r2 ? new DataView(r2.bytes.buffer).getUint32(9, true).toString(16).toUpperCase() : '-'}, shipped corpus=${JSON.stringify(flagCounts)}`);
} else {
  console.log('[+] FL corpus not available, skipping flags contrast');
}

// ---------- write dump ----------
writeFileSync(OUT_JSON, JSON.stringify(dump, null, 2) + '\n');
console.log(`\nwrote ${OUT_JSON}`);
if (fail.length) { console.error(`FAILURES: ${fail.length}`); process.exit(1); }
console.log('ALL CHECKS PASS');
