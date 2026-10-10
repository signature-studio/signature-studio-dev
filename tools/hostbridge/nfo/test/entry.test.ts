import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ValueFile } from '../src/valuefile.ts';
import {
  readEntry, writeEntry, newFile, entryToBytes, entryFromBytes, type PluginEntry,
} from '../src/entry.ts';
import {
  guidToString, guidFromString, tuidFromHex, vst2PseudoGuid, slotOf, scanFlagsFromDisk, scanFlagsToDisk, sanitizeName,
  delimitedParse, delimitedFormat, familyOf, classVariant, compressToken, expandToken,
} from '../src/format.ts';

const VST3_CID = '56534558667350736572756D20320000';

test('GUID text mapping = Windows GUID memory layout (fle 0x439300/0x4391c0)', () => {
  const b = Uint8Array.from({ length: 16 }, (_, i) => i + 1);
  assert.equal(guidToString(b), '{04030201-0605-0807-090A-0B0C0D0E0F10}');
  assert.deepEqual([...guidFromString('{04030201-0605-0807-090a-0b0c0d0e0f10}')!], [...b]);
  assert.equal(guidFromString('{04030201-0605-0807-090A-0B0C0D0E0F1}'), undefined);
  assert.equal(guidFromString('04030201-0605-0807-090A-0B0C0D0E0F10'), undefined);
  // tuidFromHex takes the CID TEXT hex (moduleinfo.json / ps_file_guid form): bytes = Windows GUID layout of it.
  // Real machine (CAB-219): Serum 2 ps_file_guid text = {56534558-6673-5073-6572-756D20320000} == the spec CID.
  assert.equal(guidToString(tuidFromHex(VST3_CID)), '{56534558-6673-5073-6572-756D20320000}');
});

test('VST2 pseudo-GUID = "VST" + magic4 chars + lower(name), 16B (real .Plugins.ini 64/64, CAB-219)', () => {
  // 'FrAr' + 'fresh air' — byte-identical to the real Fresh Air ps_file_guid {56535446-7241-7266-7265-736820616972}
  assert.equal(
    guidToString(vst2PseudoGuid('Fresh Air', 1181892978)),
    '{56535446-7241-7266-7265-736820616972}',
  );
  assert.equal(guidToString(vst2PseudoGuid('OTT', 0x58665454)), '{56535458-6654-546F-7474-000000000000}');
  // the "VSE" prefix variant (fle:0x8f0d30 param_4≠0) — not observed in real files
  assert.equal(guidToString(vst2PseudoGuid('OTT', 0x58665454, true)).slice(0, 9), '{56534558');
});

test('class tables: slots, fx/gen pairs, families', () => {
  assert.equal(slotOf(0, 2), 2); assert.equal(slotOf(0, 3), 3); assert.equal(slotOf(4, 3), 3);
  assert.equal(slotOf(7, 3), 5); assert.equal(slotOf(8, 2), 4);
  assert.equal(slotOf(2, 3), 1); assert.equal(slotOf(3, 2), 0);
  assert.equal(slotOf(9, 3), 6); assert.equal(slotOf(9, 2), -1);
  assert.equal(slotOf(11, 3), 7); assert.equal(slotOf(12, 2), -1);
  assert.equal(slotOf(1, 3), -1); assert.equal(slotOf(5, 3), -1); assert.equal(slotOf(6, 3), -1);
  assert.equal(classVariant(true, 4), 0); assert.equal(classVariant(false, 7), 8); assert.equal(classVariant(false, 11), 12);
  assert.equal(familyOf(8), 'vst3'); assert.equal(familyOf(12), 'clap'); assert.equal(familyOf(6), undefined);
});

test('scanflags disk↔memory mapping (fle 0x910590/0x910530)', () => {
  assert.equal(scanFlagsFromDisk(1), 1); assert.equal(scanFlagsFromDisk(2), 2);
  assert.equal(scanFlagsFromDisk(0x10), 4); assert.equal(scanFlagsFromDisk(0x20), 0x10); assert.equal(scanFlagsFromDisk(0x0c), 0);
  for (const d of [0, 1, 2, 3, 0x10, 0x20, 0x33]) assert.equal(scanFlagsToDisk(scanFlagsFromDisk(d)), d);
  assert.equal(scanFlagsToDisk(8), 0);
});

test('names / tokens / DelimitedText', () => {
  assert.equal(sanitizeName('A/B\\C|D?E*F"G<H>I:J'), 'A-B-C-D-E-F-G-H-I-J');
  assert.equal(sanitizeName('.hidden'), '-hidden');
  assert.equal(compressToken('C:\\FL\\Plugins\\x.dll', 'C:\\FL\\', '%FLPath%'), '%FLPath%\\Plugins\\x.dll');
  assert.equal(compressToken('D:\\x.dll', 'C:\\FL', '%FLPath%'), 'D:\\x.dll');
  assert.equal(expandToken('%FLPath%\\Plugins\\x.dll', 'C:\\FL\\', '%FLPath%'), 'C:\\FL\\Plugins\\x.dll');
  assert.deepEqual(delimitedParse('a,"b c",d'), ['a', 'b c', 'd']);
  assert.equal(delimitedFormat(['a', 'b c', 'd']), 'a,"b c",d');
  assert.deepEqual(delimitedParse(delimitedFormat(['x"y', 'p,q'])), ['x"y', 'p,q']);
});

const sample = (): PluginEntry => ({
  fileVersion: 2,
  name: 'My Synth',
  presetFilename: 'C:\\DB\\Installed\\Generators\\VST3\\My Synth.fst',
  files: [
    newFile({
      name: 'My Synth', filename: 'C:\\VST3\\My Synth.vst3', plugclass: 8, bits: 3, guid: tuidFromHex(VST3_CID),
      vendor: 'Acme', category: 'Synth', scanflags: 1, size: 123456789012n, date: 133000000000000000n, compat: ['A B', 'C'],
    }),
    newFile({ name: 'My Synth', filename: 'C:\\VST2\\My Synth.dll', plugclass: 4, bits: 2, magic: 0x80112233 | 0, type: 2 }),
  ],
});

test('writer: key order, "_<n>" suffix, default omission, signed magic', () => {
  const vf = writeEntry(sample(), { dbPath: 'C:\\DB' });
  const keys = vf.keys();
  assert.deepEqual(keys.slice(0, 5), ['fileversion', 'ps_name', 'ps_presetfilename', 'ps_files', 'ps_file_name_0']);
  assert.equal(vf.get('ps_presetfilename'), '%FLPluginDBPath%\\Installed\\Generators\\VST3\\My Synth.fst');
  assert.equal(vf.get('ps_file_bitsize_0'), '64');
  assert.equal(vf.get('ps_file_bitsize_1'), '32');
  assert.equal(vf.get('ps_file_magic_0'), undefined); // 0 omitted
  assert.equal(vf.get('ps_file_magic_1'), String(0x80112233 | 0)); // signed
  assert.equal(vf.get('ps_file_type_0'), undefined);
  assert.equal(vf.get('ps_file_type_1'), '2');
  assert.equal(vf.get('ps_file_scanflags_0'), '1');
  assert.equal(vf.get('ps_file_scanflags_1'), undefined);
  assert.equal(vf.get('ps_file_guid_1'), undefined);
  assert.equal(vf.get('ps_compatibility_0'), 'A B,C'.replace('A B', '"A B"'));
  assert.ok(vf.toString().endsWith('\r\n'));
});

test('reader(writer(x)) == x', () => {
  const e = sample();
  const r = entryFromBytes(entryToBytes(e, { dbPath: 'C:\\DB' }), { dbPath: 'C:\\DB' });
  assert.equal(r.dropped, undefined);
  assert.deepEqual(r.rejectedFiles, []);
  assert.deepEqual(r.entry, e);
});

test('reader drops exactly what FL drops', () => {
  const mk = (extra: string): ValueFile => ValueFile.parse(`fileversion=2\r\nps_name=X\r\nps_files=1\r\nps_file_filename_0=C:\\x.dll\r\n${extra}`);
  // missing plugclass → -1 → file dropped → no files → entry dropped
  assert.match(readEntry(mk('')).dropped ?? '', /no usable file/);
  // DX (class 1) / class 6 have no slot
  assert.match(readEntry(mk('ps_file_plugclass_0=1\r\n')).dropped ?? '', /no usable file/);
  // AU/CLAP are 64-bit only
  assert.match(readEntry(mk('ps_file_plugclass_0=11\r\nps_file_bitsize_0=32\r\n')).dropped ?? '', /no usable/);
  assert.equal(readEntry(mk('ps_file_plugclass_0=11\r\nps_file_bitsize_0=64\r\n')).entry?.files.length, 1);
  // bitsize anything but 64 reads as 32; type outside {1,2} → 0; unparsable GUID → null
  const ok = readEntry(mk('ps_file_plugclass_0=0\r\nps_file_bitsize_0=48\r\nps_file_type_0=5\r\nps_file_guid_0=nonsense\r\n')).entry!.files[0];
  assert.equal(ok.bits, 2); assert.equal(ok.type, 0); assert.ok(ok.guid.every((x) => x === 0));
  // ps_files=0 / unknown fileversion
  assert.ok(readEntry(ValueFile.parse('fileversion=2\r\nps_name=X\r\n')).dropped);
  assert.match(readEntry(ValueFile.parse('fileversion=3\r\nps_files=1')).dropped ?? '', /fileversion/);
});

test('case-insensitive keys, ps_file_arch names, fallback .fst next to the nfo', () => {
  const vf = ValueFile.parse('FileVersion=2\r\nPS_NAME=Y\r\nPs_Files=1\r\nPS_FILE_PLUGCLASS_0=0\r\nps_file_arch_0=apple + intel');
  const r = readEntry(vf, { nfoPath: 'C:\\DB\\Installed\\Effects\\VST\\Y.nfo', fallbackFst: true, exists: (p) => p === 'C:\\DB\\Installed\\Effects\\VST\\Y.fst' });
  assert.equal(r.entry!.files[0].arch, 3);
  assert.equal(r.entry!.presetFilename, 'C:\\DB\\Installed\\Effects\\VST\\Y.fst');
});

test('fileversion=1 legacy record expands to per-bitness files', () => {
  const vf = ValueFile.parse(['ps_name=Old', 'ps_vendorname=V', 'ps_magic=77', 'ps_plugclass=4', 'ps_category=C', 'ps_scanflags=1',
    'ps_pluginfilename_vst_32=C:\\a32.dll', 'ps_pluginfilename_vst_64=C:\\a64.dll', 'ps_pluginfilename_vst3_64=C:\\a.vst3'].join('\r\n'));
  const r = readEntry(vf);
  assert.deepEqual(r.entry!.files.map((f) => [f.plugclass, f.bits, f.filename]), [[4, 2, 'C:\\a32.dll'], [4, 3, 'C:\\a64.dll'], [8, 3, 'C:\\a.vst3']]);
  assert.equal(r.entry!.files[0].magic, 77);
});

test('"new plugin" decoration only for runtime flag 8', () => {
  const e = sample();
  e.files[0].scanflags = 8 | 1;
  const vf = writeEntry(e, { newDecoration: { tip: 'VST3 / 64 bit' } });
  assert.deepEqual(vf.keys().slice(0, 4), ['fileversion', 'iconindex', 'color', 'tip']);
  assert.equal(vf.get('ps_file_scanflags_0'), '1');
});
