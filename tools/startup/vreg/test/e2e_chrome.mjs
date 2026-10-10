// 実ブラウザ e2e: headless Chrome 上で wasm 版 vreg + IdbStore(実 IndexedDB) を動かし、ページ再読込をまたいで HKCU が永続することを検証。
//   node test/e2e_chrome.mjs     (build/vreg_wasm.mjs が必要。chrome が無ければ exit 3 でスキップ扱い)
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { launchChrome } from '../../../runtime/lib/chrome.mjs';
import { serve } from '../../../runtime/lib/serve.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srv = await serve([{ prefix: '/', dir: ROOT }], { isolate: false });
let chrome;
try {
  chrome = await launchChrome();
} catch (e) { console.error('[e2e_chrome] chrome を起動できない:', e.message); await srv.close(); process.exit(3); }
try {
  const url = `http://127.0.0.1:${srv.port}/test/chrome_page.html`;
  const page = await chrome.newPage(url);
  await page.waitFor('ready', 30000);
  const p1 = await page.evaluate('window.phase1()');
  assert.equal(p1.restored, false); assert.equal(p1.reg, true);
  assert.equal(p1.engine, 'C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll');
  await page.goto(url);                                   // 本物のページ再読込
  await page.waitFor('ready', 30000);
  const p2 = await page.evaluate('window.phase2()');
  assert.equal(p2.restored, true); assert.equal(p2.run, 321); assert.equal(p2.sessionOnly, false); assert.equal(p2.guid, p1.guid); assert.equal(p2.reg, true);
  await page.goto(url);
  await page.waitFor('ready', 30000);
  const p3 = await page.evaluate('window.phase3()');
  assert.equal(p3.mode, 'trial'); assert.equal(p3.reg, false); assert.equal(p3.run, 321);
  assert.deepEqual(page.exceptions, []);
  console.log(`[e2e_chrome] PASS (${chrome.version}): phase1 新規 → reload → 復元 run=${p2.run} guid 安定 / HKLM 非永続 / trial 切替 reg=${p3.reg}`);
} finally { await chrome.close(); await srv.close(); }
