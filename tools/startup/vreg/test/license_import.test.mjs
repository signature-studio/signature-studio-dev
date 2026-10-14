// .reg 取込入口の入力検査 (checkUserReg) の単体テスト。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkUserReg } from '../js/license_import.mjs';
import { encodeUtf16le } from '../js/regfile.mjs';

const TEXT = 'Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\Example]\r\n"A"="1"\r\n"B"=dword:00000002\r\n';

test('checkUserReg: UTF-16LE (BOM) / UTF-8 (BOM) / BOM 無し UTF-16LE を受理し値数を返す', () => {
  const utf8bom = new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode(TEXT)]);
  const noBom = encodeUtf16le(TEXT, false);
  assert.deepEqual(checkUserReg(encodeUtf16le(TEXT, true)), { values: 2 });
  assert.deepEqual(checkUserReg(utf8bom), { values: 2 });
  assert.deepEqual(checkUserReg(noBom), { values: 2 });
});

test('checkUserReg: ヘッダ不一致と値なしは throw', () => {
  assert.throws(() => checkUserReg(new TextEncoder().encode('hello\n')), /1 行目/);
  assert.throws(() => checkUserReg(new TextEncoder().encode('Windows Registry Editor Version 5.00\n\n[HKEY_CURRENT_USER\\Software\\Example]\n')), /値がありません/);
});
