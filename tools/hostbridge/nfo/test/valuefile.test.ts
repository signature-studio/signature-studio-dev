import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ValueFile, strToIntDef, strToInt64Def, decodeText, encodeText } from '../src/valuefile.ts';
import { readNativePluginNfo } from '../src/entry.ts';
import { FL_ROOT, HAVE_FL, filesWithExt, read } from './_fl.ts';

test('strToIntDef follows Delphi StrToIntDef', () => {
  assert.equal(strToIntDef('12', 0), 12);
  assert.equal(strToIntDef(' -7', 0), -7);
  assert.equal(strToIntDef('$FF', 0), 255);
  assert.equal(strToIntDef('0x10', 0), 16);
  assert.equal(strToIntDef('abc', 5), 5);
  assert.equal(strToIntDef('', 5), 5);
  assert.equal(strToIntDef(undefined, 9), 9);
  assert.equal(strToInt64Def('9223372036854775807', 0n), 9223372036854775807n);
  assert.equal(strToInt64Def('9223372036854775808', 3n), 3n);
});

test('lookup: case-insensitive key, first match wins, apostrophe lines are comments', () => {
  const vf = ValueFile.parse("' note\r\nPS_Name=A=B\r\nps_name=second\r\n'ps_x=hidden\r\nps_x=1");
  assert.equal(vf.get('ps_name'), 'A=B');
  assert.equal(vf.get('PS_X'), '1');
  assert.equal(vf.get('missing'), undefined);
  assert.equal(vf.getInt('ps_x', 0), 1);
});

test('lossless: mixed EOLs, missing trailing EOL, BOM', () => {
  for (const t of ['a=1\r\nb=2\r\n', 'a=1\nb=2', 'a=1\r\n\r\n', '', 'x', '\ufeffa=1\r\nb=2\n', 'a=1\rb=2\r\n']) {
    assert.equal(ValueFile.parse(t).toString(), t, JSON.stringify(t));
  }
});

test('text codec: ascii as-is, non-ascii gets a UTF-8 BOM, BOM/UTF-16 decode', () => {
  assert.deepEqual([...encodeText('a=b')], [97, 61, 98]);
  const b = encodeText('ps_name=Möbius');
  assert.deepEqual([...b.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  assert.equal(decodeText(b), 'ps_name=Möbius');
  assert.equal(decodeText(Uint8Array.of(0xff, 0xfe, 0x61, 0, 0x3d, 0, 0x62, 0)), 'a=b');
});

test('shipped .nfo corpus (browser info files + Plugin.nfo) round-trips byte-exact', { skip: !HAVE_FL }, () => {
  const files = filesWithExt(FL_ROOT, '.nfo');
  assert.ok(files.length >= 800, `found ${files.length}`);
  let bad = 0;
  for (const f of files) {
    const raw = read(f);
    if (raw.some((x) => x > 0x7f)) continue; // none in FL 26.1.7; non-ASCII would need the ANSI code page
    const txt = decodeText(raw);
    if (ValueFile.parse(txt).toString() !== txt) bad++;
  }
  assert.equal(bad, 0);
});

test('Plugin.nfo of native Fruity plugins: ps_vendorname (any case) + optional ps_dummy64bit', { skip: !HAVE_FL }, () => {
  const files = filesWithExt(`${FL_ROOT}/Plugins/Fruity`, 'plugin.nfo');
  assert.equal(files.length, 141);
  let dummy = 0;
  for (const f of files) {
    const r = readNativePluginNfo(ValueFile.parse(decodeText(read(f))));
    assert.equal(r.vendor, 'Image-Line');
    if (r.dummy64bit) dummy++;
  }
  assert.equal(dummy, 2);
});
