import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { ROOT } from './helpers.mjs';
import { decodeRegBytes, encodeUtf16le, parseToModel } from '../js/regfile.mjs';

test('CLI: UTF-16LE .reg を import → 別プロセスで export して内容が残る', () => {
  const work = path.join(ROOT, 'work/cli-' + process.pid); mkdirSync(work, { recursive: true });
  const inp = path.join(work, 'in.reg'), out = path.join(work, 'out.reg');
  writeFileSync(inp, encodeUtf16le('Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\CliT]\r\n"名前"="値あ"\r\n"n"=dword:00000007\r\n', true));
  const run = (...a) => spawnSync(process.execPath, [path.join(ROOT, 'js/cli.mjs'), ...a, '--dir', work + '/prof'], { encoding: 'utf8' });
  let r = run('import', inp); assert.equal(r.status, 0, r.stderr);
  r = run('export', out, '--hives', 'HKCU'); assert.equal(r.status, 0, r.stderr);
  const bytes = readFileSync(out); assert.deepEqual([bytes[0], bytes[1]], [0xff, 0xfe]);
  const m = parseToModel(decodeRegBytes(bytes));
  assert.deepEqual(m.HKCU['Software\\CliT'], { 名前: { t: 'REG_SZ', v: '値あ' }, n: { t: 'REG_DWORD', v: 7 } });
  r = run('export', out + '8', '--utf8', '--hives', 'HKCU'); assert.equal(r.status, 0);
  assert.match(readFileSync(out + '8', 'utf8'), /^Windows Registry Editor Version 5\.00/);
});
