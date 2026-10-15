// 実ブラウザ e2e: .reg 取込入口 (ui/import.html) を headless Chrome で操作し、取込と MachineGuid 設定が再読込をまたいで残ることを検証。
//   node test/e2e_import_ui.mjs   (build/vreg_wasm.mjs が必要。chrome が無ければ exit 3 でスキップ扱い)
//   取込に使う .reg は本テスト内の合成フィクスチャ (実ライセンスではない)。
import path from 'node:path';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { launchChrome } from '../../../runtime/lib/chrome.mjs';
import { serve } from '../../../runtime/lib/serve.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const seed = JSON.parse(readFileSync(path.join(ROOT, 'data/seed.json'), 'utf8'));
const FIXTURE_KEY = 'E2E-FIXTURE-NOT-A-LICENSE';
const FIXTURE_TEXT = [
  'Windows Registry Editor Version 5.00', '',
  '[HKEY_CURRENT_USER\\Software\\Image-Line\\Registrations\\FL Studio 26.1]', `"ILRegKey"="${FIXTURE_KEY}"`, '',
  '[HKEY_CURRENT_USER\\Software\\Image-Line\\Registrations\\FL Data]', `"ILRegKey"="${FIXTURE_KEY}"`, '',
  '[HKEY_CURRENT_USER\\Software\\Image-Line\\E2E-Import]', '"Marker"="imported"', '',
].join('\r\n');
const FIXTURE_B64 = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(FIXTURE_TEXT, 'utf16le')]).toString('base64');
const BAD_B64 = Buffer.from('hello, not a reg file\n', 'utf8').toString('base64');
const GUID_IN = 'ABCDEF01-2345-6789-ABCD-EF0123456789';
const GUID = GUID_IN.toLowerCase();
const GUID_ENTRY = seed.entries.find((e) => e.name === 'MachineGuid' && e.key);
const REG_KEY = 'Software\\Image-Line\\Registrations\\FL Studio 26.1';

// 指定 base64 の内容を持つ File を input[type=file] に入れて change を発火する (実 UI の経路と同じ handler を通す)
const pickFile = (b64, name) => `(() => {
  const bin = atob(${JSON.stringify(b64)}), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const dt = new DataTransfer(); dt.items.add(new File([u], ${JSON.stringify(name)}));
  const input = document.getElementById('reg-file'); input.files = dt.files;
  input.dispatchEvent(new Event('change')); return true;
})()`;
const msgText = `document.getElementById('msg').textContent`;
const regValue = (hive, key, name) => `window.licenseImport.vreg.readStr(${JSON.stringify(hive)}, ${JSON.stringify(key)}, ${JSON.stringify(name)}).value`;

const srv = await serve([{ prefix: '/', dir: ROOT }], { isolate: false });
let chrome;
try {
  chrome = await launchChrome();
} catch (e) { console.error('[e2e_import_ui] chrome を起動できない:', e.message); await srv.close(); process.exit(3); }
try {
  const url = `http://127.0.0.1:${srv.port}/ui/import.html`;
  const page = await chrome.newPage(url);
  await page.waitFor('ready', 30000);

  // 1) 初回 (取込なし): 既定は登録済み (seed の placeholder)
  const s1 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s1.restored, false); assert.equal(s1.licenseMode, 'registered'); assert.equal(s1.registered, true); assert.equal(s1.userReg, null);
  const placeholder = await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey'));
  assert.ok(placeholder && placeholder !== FIXTURE_KEY, 'placeholder が入っている');

  // 2) 正規の .reg を取り込む → external モードで登録済み、値は取込んだもの
  const before = await page.evaluate(msgText);
  await page.evaluate(pickFile(FIXTURE_B64, 'user-export.reg'));
  await page.waitForExpr(`${msgText} !== ${JSON.stringify(before)}`);
  assert.match(await page.evaluate(msgText), /取り込みました: user-export\.reg \(値 3 件\)/);
  const s2 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s2.licenseMode, 'external'); assert.equal(s2.registered, true); assert.equal(s2.userReg.name, 'user-export.reg');
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);
  assert.equal(await page.evaluate(regValue('HKCU', 'Software\\Image-Line\\E2E-Import', 'Marker')), 'imported');

  // 3) 不正なファイルは拒否し、取込済みの状態を変えない
  const before3 = await page.evaluate(msgText);
  await page.evaluate(pickFile(BAD_B64, 'bad.reg'));
  await page.waitForExpr(`${msgText} !== ${JSON.stringify(before3)}`);
  assert.match(await page.evaluate(msgText), /取り込み失敗/);
  const s3 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s3.userReg.name, 'user-export.reg');
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);

  // 4) MachineGuid をユーザ指定 (大文字入力 → 小文字で保存)。不正形式は拒否
  await page.evaluate(`(() => { document.getElementById('machine-guid').value = ${JSON.stringify(GUID_IN)}; document.getElementById('apply-guid').click(); return true; })()`);
  await page.waitForExpr(`${msgText} === 'MachineGuid を設定しました'`);
  const s4 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s4.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue(GUID_ENTRY.hive, GUID_ENTRY.key, 'MachineGuid')), GUID);
  await page.evaluate(`(() => { document.getElementById('machine-guid').value = 'xyz'; document.getElementById('apply-guid').click(); return true; })()`);
  await page.waitForExpr(`${msgText}.startsWith('MachineGuid 設定失敗')`);
  assert.equal((await page.evaluate('window.licenseImport.status()')).machineGuid, GUID);

  // 5) 再読込 (本物のページ再読込): 取込と MachineGuid が残り、既定の placeholder には戻らない
  await page.goto(url);
  await page.waitFor('ready', 30000);
  const s5 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s5.restored, true); assert.equal(s5.licenseMode, 'external'); assert.equal(s5.registered, true);
  assert.equal(s5.userReg.name, 'user-export.reg'); assert.equal(s5.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);
  assert.equal(await page.evaluate(regValue('HKCU', 'Software\\Image-Line\\E2E-Import', 'Marker')), 'imported');
  assert.equal(await page.evaluate(regValue(GUID_ENTRY.hive, GUID_ENTRY.key, 'MachineGuid')), GUID);
  assert.deepEqual(page.exceptions, []);
  console.log(`[e2e_import_ui] PASS (${chrome.version}): 初回 placeholder → 取込(external) → 不正拒否 → MachineGuid 設定 → reload で取込・GUID 維持`);
} finally { await chrome.close(); await srv.close(); }
