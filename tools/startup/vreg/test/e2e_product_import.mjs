// 実ブラウザ e2e: 製品ページ (vite build の bundle・?license=import) の .reg 取込入口を headless Chrome で操作する。
//   取込 → 不正拒否 → MachineGuid 設定 → reload で保持 → 取消しで既定 (登録済み placeholder) に戻る → reload で戻ったまま。
//   既定ページ (?license なし) では入口が無いことも確認する。ui/import.html の e2e (e2e_import_ui.mjs) と同じ検査を製品側で行う。
//   node test/e2e_product_import.mjs   (build/vreg_wasm.mjs が必要。chrome が無ければ exit 3 でスキップ扱い)
//   bundle は repo の vite で $RUNTIME_TMP (無ければ tmpdir) に作ってから配信する (tools/startup/vreg/work/ は使わない)。
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { launchChrome } from '../../../runtime/lib/chrome.mjs';
import { serve } from '../../../runtime/lib/serve.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO = path.resolve(ROOT, '../../..');
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
const MARKER = ['HKCU', 'Software\\Image-Line\\E2E-Import', 'Marker'];

const pickFile = (b64, name) => `(() => {
  const bin = atob(${JSON.stringify(b64)}), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const dt = new DataTransfer(); dt.items.add(new File([u], ${JSON.stringify(name)}));
  const input = document.getElementById('license-file'); input.files = dt.files;
  input.dispatchEvent(new Event('change')); return true;
})()`;
const clickId = (id, guid) => `(() => {
  ${guid !== undefined ? `document.getElementById('license-guid').value = ${JSON.stringify(guid)};` : ''}
  document.getElementById(${JSON.stringify(id)}).click(); return true;
})()`;
const msgText = `document.getElementById('license-msg').textContent`;
const regValue = (hive, key, name) => `window.licenseImport.vreg.readStr(${JSON.stringify(hive)}, ${JSON.stringify(key)}, ${JSON.stringify(name)}).value`;
const hasValue = (hive, key, name) => `window.licenseImport.vreg.valueExists(${JSON.stringify(hive)}, ${JSON.stringify(key)}, ${JSON.stringify(name)})`;

const VITE = path.join(REPO, 'node_modules/.bin/vite');
if (!existsSync(VITE)) { console.error('[e2e_product_import] node_modules/.bin/vite が無い (リポジトリ root で pnpm install が要る)'); process.exit(3); }
const OUT = path.join(process.env.RUNTIME_TMP ?? os.tmpdir(), 'vreg-product-dist');
execFileSync(VITE, ['build', '--outDir', OUT, '--emptyOutDir', '--logLevel', 'error'], { cwd: REPO, stdio: 'inherit' });
assert.ok(existsSync(path.join(OUT, 'index.html')), 'vite build の出力が無い');

const srv = await serve([{ prefix: '/', dir: OUT }], { isolate: false });
let chrome;
try {
  chrome = await launchChrome();
} catch (e) { console.error('[e2e_product_import] chrome を起動できない:', e.message); await srv.close(); process.exit(3); }
try {
  const base = `http://127.0.0.1:${srv.port}/index.html`;
  const url = `${base}?license=import`;

  // 0) 既定ページ (?license なし): 入口も vreg も載らない
  const plain = await chrome.newPage(base);
  await new Promise((r) => setTimeout(r, 1500));
  assert.equal(await plain.evaluate(`!!document.getElementById('license-file') || !!window.licenseImport`, { awaitPromise: false }), false);

  // 1) 製品ページで取込入口を開く。初回は既定の登録済み (seed の placeholder)
  const page = await chrome.newPage(url);
  await page.waitFor('licenseImportReady', 60000);
  const s1 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s1.restored, false); assert.equal(s1.licenseMode, 'registered'); assert.equal(s1.registered, true); assert.equal(s1.userReg, null);
  const placeholder = await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey'));
  assert.ok(placeholder && placeholder !== FIXTURE_KEY, 'placeholder が入っている');

  // 2) 正規の .reg を取り込む → external・登録済み・値は取込んだもの
  await page.evaluate(pickFile(FIXTURE_B64, 'user-export.reg'));
  await page.waitForExpr(`${msgText}.startsWith('取り込みました')`);
  assert.match(await page.evaluate(msgText), /取り込みました: user-export\.reg \(値 3 件\)/);
  const s2 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s2.licenseMode, 'external'); assert.equal(s2.registered, true); assert.equal(s2.userReg.name, 'user-export.reg');
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);
  assert.equal(await page.evaluate(regValue(...MARKER)), 'imported');

  // 3) 不正なファイルは拒否し、取込済みの状態を変えない
  await page.evaluate(pickFile(BAD_B64, 'bad.reg'));
  await page.waitForExpr(`${msgText}.startsWith('取り込み失敗')`);
  const s3 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s3.userReg.name, 'user-export.reg');
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);

  // 4) MachineGuid をユーザ指定 (大文字入力 → 小文字で保存)。不正形式は拒否して保持値を変えない
  await page.evaluate(clickId('license-guid-apply', GUID_IN));
  await page.waitForExpr(`${msgText} === 'MachineGuid を設定しました'`);
  const s4 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s4.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue(GUID_ENTRY.hive, GUID_ENTRY.key, 'MachineGuid')), GUID);
  await page.evaluate(clickId('license-guid-apply', 'xyz'));
  await page.waitForExpr(`${msgText}.startsWith('MachineGuid 設定失敗')`);
  assert.equal((await page.evaluate('window.licenseImport.status()')).machineGuid, GUID);

  // 5) 再読込: 取込と MachineGuid が残る
  await page.goto(url);
  await page.waitFor('licenseImportReady', 60000);
  const s5 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s5.restored, true); assert.equal(s5.licenseMode, 'external'); assert.equal(s5.registered, true);
  assert.equal(s5.userReg.name, 'user-export.reg'); assert.equal(s5.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), FIXTURE_KEY);
  assert.equal(await page.evaluate(regValue(...MARKER)), 'imported');

  // 6) 取消し: 取込を消し、既定の登録済み (placeholder) に戻す。取込由来の seed 外の値 (Marker) も消える。MachineGuid は残る
  await page.evaluate(clickId('license-revert'));
  await page.waitForExpr(`${msgText} === '取込を取り消しました (既定の登録済みに戻しました)'`);
  const s6 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s6.licenseMode, 'registered'); assert.equal(s6.registered, true); assert.equal(s6.userReg, null);
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), placeholder);
  assert.equal(await page.evaluate(hasValue(...MARKER)), false);
  assert.equal(s6.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue(GUID_ENTRY.hive, GUID_ENTRY.key, 'MachineGuid')), GUID);
  await page.evaluate(clickId('license-revert'));
  await page.waitForExpr(`${msgText} === '取り消す取込はありません'`);

  // 7) 取消し後に再読込しても既定のまま (取込は戻らない)
  await page.goto(url);
  await page.waitFor('licenseImportReady', 60000);
  const s7 = await page.evaluate('window.licenseImport.status()');
  assert.equal(s7.restored, true); assert.equal(s7.licenseMode, 'registered'); assert.equal(s7.userReg, null); assert.equal(s7.machineGuid, GUID);
  assert.equal(await page.evaluate(regValue('HKCU', REG_KEY, 'ILRegKey')), placeholder);
  assert.equal(await page.evaluate(hasValue(...MARKER)), false);
  assert.deepEqual(page.exceptions, []);
  console.log(`[e2e_product_import] PASS (${chrome.version}): 既定ページに入口なし → 製品ページで 初回 placeholder → 取込(external) → 不正拒否 → MachineGuid 設定 → reload で保持 → 取消し(既定へ) → reload で既定のまま`);
} finally { await chrome.close(); await srv.close(); }
