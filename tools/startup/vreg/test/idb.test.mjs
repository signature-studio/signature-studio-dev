// IdbStore (IndexedDB アダプタ) のテスト。node では FakeIDB、実ブラウザでは e2e_chrome.mjs が同じ IdbStore を実 IndexedDB で検証。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boot, GEN } from './helpers.mjs';
import { IdbStore } from '../js/store.mjs';
import { FakeIDBFactory } from './fake_idb.mjs';

test('IdbStore: load/save/delete と構造化複製', async () => {
  const s = new IdbStore({ indexedDB: new FakeIDBFactory() });
  assert.equal(await s.load('p'), undefined);
  const rec = { schema: 1, hkcu: { 'Software\\X': { a: { t: 'REG_SZ', v: 'あ' } } } };
  await s.save('p', rec);
  const got = await s.load('p'); assert.deepEqual(got, rec); assert.notEqual(got, rec);
  await s.delete('p'); assert.equal(await s.load('p'), undefined);
});

test('Vreg × IdbStore: 「ページ再読込」(新 wasm + 新 IdbStore, 同じ IDB) で HKCU が復元される', async () => {
  const idb = new FakeIDBFactory();
  const a = await boot({ store: new IdbStore({ indexedDB: idb }) });
  const guid = a.machineGuid;
  a.writeInt('HKCU', GEN, 'Run counter', 12); await a.flush();
  const b = await boot({ store: new IdbStore({ indexedDB: idb }) });
  assert.equal(b.bootInfo.restored, true);
  assert.equal(b.readInt('HKCU', GEN, 'Run counter', 0), 12);
  assert.equal(b.machineGuid, guid);
});
