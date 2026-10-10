import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as R from '../js/regfile.mjs';

const SAMPLE = [
  'Windows Registry Editor Version 5.00', '',
  '[HKEY_CURRENT_USER\\Software\\X]', '@="def"', '"a b"="q\\\\w\\"z"', '"日本語"="値あ😀"', '"n"=dword:0000000a',
  '"m"=hex(7):61,00,00,00,62,00,00,00,00,00', '"b"=hex:01,02,\\', '  03', '"q"=hex(b):ff,00,00,00,00,00,00,00',
  '"e"=hex(2):25,00,50,00,25,00,00,00', '"odd"=hex(99):01,02', '',
  '[-HKEY_CURRENT_USER\\Software\\Y]', '[HKEY_LOCAL_MACHINE\\SOFTWARE\\Z]', '"gone"=-', '',
].join('\r\n');

test('parse: 全型 / エスケープ / 継続行 / 削除', () => {
  const ops = R.parseReg(SAMPLE);
  const set = Object.fromEntries(ops.filter((o) => o.op === 'set' && o.hive === 'HKCU').map((o) => [o.name, o]));
  assert.equal(set[''].v, 'def');
  assert.equal(set['a b'].v, 'q\\w"z');
  assert.equal(set['日本語'].v, '値あ😀');
  assert.deepEqual([set.n.t, set.n.v], ['REG_DWORD', 10]);
  assert.deepEqual([set.m.t, set.m.v], ['REG_MULTI_SZ', ['a', 'b']]);
  assert.deepEqual([set.b.t, set.b.v], ['REG_BINARY', '01,02,03']);
  assert.deepEqual([set.q.t, set.q.v], ['REG_QWORD', '255']);
  assert.deepEqual([set.e.t, set.e.v], ['REG_EXPAND_SZ', '%P%']);
  assert.deepEqual([set.odd.t, set.odd.v], ['REG_0x99', '01,02']);
  assert.ok(ops.some((o) => o.op === 'delkey' && o.key === 'Software\\Y'));
  assert.ok(ops.some((o) => o.op === 'delvalue' && o.hive === 'HKLM' && o.name === 'gone'));
});

test('serialize → parse は恒等 (全型)', () => {
  const m = R.parseToModel(SAMPLE);
  const m2 = R.parseToModel(R.serializeReg(m, { hives: R.ROOTS }));
  assert.deepEqual(m2, m);
});

test('UTF-16LE (BOM, CRLF) / UTF-8 BOM / BOM 無し UTF-16LE を同一内容に復号', () => {
  const m = R.parseToModel(SAMPLE);
  const bytes = R.regBytes(m, { hives: R.ROOTS });
  assert.deepEqual([...bytes.subarray(0, 2)], [0xff, 0xfe]);
  assert.ok(new TextDecoder('utf-16le').decode(bytes).includes('\r\n'));
  assert.deepEqual(R.parseToModel(bytes), m);
  const u8 = new TextEncoder().encode('\uFEFF' + R.serializeReg(m, { hives: R.ROOTS }));
  assert.deepEqual(R.parseToModel(u8), m);
  assert.deepEqual(R.parseToModel(bytes.subarray(2)), m);        // BOM 無し UTF-16LE
});

test('model: 大小無視のキー/値名、非破壊 fillMissing', () => {
  const m = R.emptyModel();
  R.setValue(m, 'HKCU', 'Software\\Foo', 'Bar', 'REG_SZ', '1');
  R.setValue(m, 'HKCU', 'software\\FOO', 'BAR', 'REG_SZ', '2');
  assert.deepEqual(Object.keys(m.HKCU), ['Software\\Foo']);
  assert.deepEqual(m.HKCU['Software\\Foo'], { BAR: { t: 'REG_SZ', v: '2' } });
  const seedM = R.emptyModel(); R.setValue(seedM, 'HKCU', 'SOFTWARE\\foo', 'bar', 'REG_SZ', 'seed'); R.setValue(seedM, 'HKCU', 'Software\\Foo', 'new', 'REG_SZ', 'n');
  R.fillMissing(m.HKCU, seedM.HKCU);
  assert.equal(R.getValue(m, 'HKCU', 'Software\\Foo', 'bar').v, '2');   // 既存は保持
  assert.equal(R.getValue(m, 'HKCU', 'Software\\Foo', 'new').v, 'n');   // 不足分のみ補う
  assert.equal(R.deleteKey(m, 'HKCU', 'software\\foo'), 1);
});

test('splitPath: 長短ルート名・先頭 \\ 許容、未知ルートは null', () => {
  assert.deepEqual(R.splitPath('HKEY_LOCAL_MACHINE\\A\\B'), { hive: 'HKLM', key: 'A\\B' });
  assert.deepEqual(R.splitPath('\\hkcu'), { hive: 'HKCU', key: '' });
  assert.equal(R.splitPath('HKEY_NOPE\\A'), null);
});
