// e2e — pathreg インタフェース接続の node 実行検証 (モック永続化層)。
//   前提: bash scripts/build.sh all 済 (build/module_a.mjs / build/module_b.mjs)。
//   実行: node test/e2e.mjs  (scripts/e2e.sh が 1 コマンド化)
//
// 検証内容:
//   A. module-a (vreg_* フック export = 本番構成; reg.c は shimx 正本): RegBridge で seed→書込→flush→「再起動」→復元。
//      flush タイミング契約 (遅延 / onYield / onPageHide / ブロック中は保存されない)。
//      ★ 本物の vreg Vreg アダプタ (tools/startup/vreg/js/vreg.mjs) が同じ store レコードを読める相互運用。
//   B. module-b (フック非 export = 代替構成; 通知口なし経路): 同様の往復 + built-in 既定値の削除が永続すること
//      (shimx_reg_reset による復活を _applyDeletions が消す) + hash 変更検出。
//   C. パス写像 C (pathreg_map) ↔ JS (pathmap.mjs) のクロスチェック (fixture 全件一致 + 逆写像)。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import { RegBridge } from '../js/regbridge.mjs';
import { createMapper, defaultMounts } from '../js/pathmap.mjs';
import { MemoryStore } from '../../../startup/vreg/js/store.mjs';
import { Vreg } from '../../../startup/vreg/js/vreg.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const seed = JSON.parse(readFileSync(path.join(ROOT, '../../startup/vreg/data/seed.json'), 'utf8'));
const createA = (await import(path.join(ROOT, 'build/module_a.mjs'))).default;
const createB = (await import(path.join(ROOT, 'build/module_b.mjs'))).default;

const GEN = 'Software\\Image-Line\\FL Studio 26\\General';
const PATHS = 'Software\\Image-Line\\Shared\\Paths';
const INTL = 'Control Panel\\International';
let pass = 0;
const ok = (msg) => { pass++; console.log(`OK e2e: ${msg}`); };

// ---------------------------------------------------------------- A. module-a (vreg_* フック結線)
{
  const store = new MemoryStore();
  const bridge = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  assert.equal(bridge.bootInfo.link, 'vreg');
  assert.equal(bridge.bootInfo.restored, false);
  assert.ok(bridge.machineGuid);
  // seed の Paths 値が入っている
  assert.equal(bridge.readStr('HKCU', PATHS, 'Shared data'), 'C:\\Users\\webstudio\\Documents\\Image-Line\\');
  // ライセンス (既定 registered): ILRegKey が有る
  assert.equal(bridge.observeRegistration().registered, true);

  // エンジン相当の書込 → 遅延 flush 経由で永続 (shimx reg.c の通知フック vreg_set_notify → dirty → setTimeout)
  const b2 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 100 });
  assert.equal(b2.bootInfo.restored, true);
  b2.writeStr('HKCU', GEN, 'LastProject', 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Projects\\demo.flp');
  b2.writeInt('HKCU', GEN, 'Run counter', 41);
  assert.equal(b2.dirty, true);
  await new Promise((r) => setTimeout(r, 30));            // 遅延中 (未保存)
  assert.notEqual(store.m.get('p-a').hkcu[GEN]['Run counter']?.v, 41, '遅延 flush 前は未保存 (seed 既定 0 のまま)');
  await new Promise((r) => setTimeout(r, 300));           // 遅延 flush 発火
  assert.equal(store.m.get('p-a').hkcu[GEN]['Run counter'].v, 41);
  ok(`A1: seed 適用 + 遅延 flush (flushes=${b2.flushes})`);

  // onYield / onPageHide の明示口
  const b3 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 60000 });
  b3.writeInt('HKCU', GEN, 'Run counter', 42);
  await b3.onYield();                                     // yield 点で即畳み
  assert.equal(store.m.get('p-a').hkcu[GEN]['Run counter'].v, 42);
  b3.writeStr('HKCU', GEN, 'LastProject', 'x.flp');
  await b3.onPageHide();                                  // pagehide で即畳み
  assert.equal(store.m.get('p-a').hkcu[GEN].LastProject.v, 'x.flp');
  ok('A2: onYield / onPageHide flush');

  // ブロック中 (yield 無し) は保存されない = flush 点契約の根拠
  const b4 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  b4.writeInt('HKCU', GEN, 'Run counter', 43);            // flushDelayMs=0 → 遅延無し。それでも明示 flush が無ければ…
  const b5 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  assert.equal(b5.readStr('HKCU', GEN, 'Run counter'), 42, 'yield 無しの変更は次セッションに載らない (flush 点のみ保存)');
  await b4.flush();                                        // 明示 flush すれば載る
  const b6 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  assert.equal(b6.readStr('HKCU', GEN, 'Run counter'), 43);
  ok('A3: flush 点契約 (yield 無しは未保存 / flush で保存)');

  // ★ 本物の vreg Vreg アダプタとの相互運用 (同一 store / 同一 seed)
  const vreg = await Vreg.create({ createModule: () => createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  assert.equal(vreg.machineGuid, bridge.machineGuid);
  assert.equal(vreg.readInt('HKCU', GEN, 'Run counter'), 43);           // bridge が書いた値を vreg が読む
  assert.equal(vreg.observeRegistration().registered, true);
  vreg.writeInt('HKCU', GEN, 'Run counter', 44);
  await vreg.flush();
  const b7 = await RegBridge.create({ mod: await createA(), store, seed, profile: 'p-a', flushDelayMs: 0 });
  assert.equal(b7.readInt('HKCU', GEN, 'Run counter'), 44);             // vreg が書いた値を bridge が読む
  const rec = store.m.get('p-a');
  assert.deepEqual(Object.keys(rec).sort(), ['hkcu', 'machineGuid', 'savedAt', 'schema', 'seedVersion']);
  ok(`A4: vreg Vreg 相互運用 (レコード互換, keys=${Object.keys(rec.hkcu).length})`);
}

// ---------------------------------------------------------------- B. module-b (フック非 export)
{
  const store = new MemoryStore();
  const bridge = await RegBridge.create({ mod: await createB(), store, seed, profile: 'p-b', flushDelayMs: 0 });
  assert.equal(bridge.bootInfo.link, 'shimx');
  assert.equal(bridge.readStr('HKCU', PATHS, 'Shared data'), 'C:\\Users\\webstudio\\Documents\\Image-Line\\');

  bridge.writeInt('HKCU', GEN, 'Run counter', 7);
  bridge.writeStr('HKCU', GEN, 'LastProject', 'C:\\proj.flp');
  // built-in 既定値 (shimx_reg_reset が復活させる) の削除が永続するか
  bridge.deleteValue('HKCU', INTL, 'sDecimal');
  assert.ok(await bridge.flush());                        // hash 差分 → 保存
  assert.ok(!bridge.valueExists('HKCU', INTL, 'sDecimal'));
  assert.equal(bridge.readInt('HKCU', GEN, 'Run counter'), 7);

  const r2 = await RegBridge.create({ mod: await createB(), store, seed, profile: 'p-b', flushDelayMs: 0 });
  assert.equal(r2.readInt('HKCU', GEN, 'Run counter'), 7);
  assert.equal(r2.readStr('HKCU', GEN, 'LastProject'), 'C:\\proj.flp');
  assert.equal(r2.valueExists('HKCU', INTL, 'sDecimal'), false, 'built-in 既定の削除が復元後も保持される (_applyDeletions)');
  assert.equal(r2.valueExists('HKCU', INTL, 'sThousand'), true, '既定の他値は残る');
  assert.equal(r2.machineGuid, bridge.machineGuid);
  assert.ok(await r2.flush() === false, '直後の flush は無変更なので no-op (hash 変更検出)');
  ok(`B: shimx reg.c 構成の往復 + 削除永続 + hash 検出 (keys=${r2.stats().keys})`);
}

// ---------------------------------------------------------------- C. C ↔ JS 写像クロスチェック
{
  const mod = await createB();
  mod._shimx_init();
  mod._pathreg_install();
  const mapper = createMapper();
  const fixtures = [
    'C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp',
    'C:\\PROGRAM FILES\\Image-Line\\FL Studio 2026\\Plugins\\Fruity\\Effects\\Fruity Send\\Fruity Send_x64.dll',
    'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT.nfo',
    'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\VerifiedIDs.nfo',
    'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml',
    'C:\\Users\\webstudio\\AppData\\Roaming\\Image-Line\\Shared\\config.xml',
    'C:\\Users\\webstudio\\AppData\\Local\\Temp\\Image-Line\\9-2\\zip\\inner.bin',
    'C:\\Users\\webstudio\\AppData\\Local\\Image-Line\\QuickFontCache.dat',
    'C:\\Users\\user\\Documents\\Image-Line\\retired.txt',   // 退役した予備 profile: 残余 C: 規則で C/JS 一致
    'C:\\Windows\\notepad.exe',
    'C:\\foo\\..\\bar\\./x',
    'D:\\unmapped\\path.txt',
    '/posix/abs/path',
    'relative\\win\\path',
    '\\\\?\\C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\x.wav',
    '\\\\srv\\share\\folder\\file.dat',
  ];
  const inBuf = mod._malloc(2048), outBuf = mod._malloc(2048);
  const cmap = (p) => {
    mod.stringToUTF8(p, inBuf, 2048);
    const r = mod._pathreg_map(inBuf, outBuf, 2048);
    return { r, out: r === 0 ? mod.UTF8ToString(outBuf) : null };
  };
  const cunmap = (p) => {
    mod.stringToUTF8(p, inBuf, 2048);
    const r = mod._pathreg_unmap(inBuf, outBuf, 2048);
    return { r, out: r === 0 ? mod.UTF8ToString(outBuf) : null };
  };
  for (const f of fixtures) {
    const c = cmap(f), j = mapper.map(f);
    assert.equal(c.out, j, `map mismatch: ${f} (C=${c.out} JS=${j})`);
    assert.equal(c.r === 0, j !== null, `map rc mismatch: ${f}`);
    if (c.out) {
      const cu = cunmap(c.out), ju = mapper.unmap(c.out);
      assert.equal(cu.out, ju, `unmap mismatch: ${c.out}`);
    }
  }
  // 追加マウント (C add_mount ↔ JS extraMounts) も一致させる
  {
    const wp = (s) => { const p = mod._malloc(s.length + 1); mod.stringToUTF8(s, p, s.length + 1); return p; };
    const a = wp('E:\\SampleLib'), b = wp('/libs/sample');
    assert.equal(mod._pathreg_add_mount(a, b, 1), 0);
    mod._free(a); mod._free(b);
  }
  const mapper2 = createMapper({ extraMounts: [{ win: 'E:\\SampleLib', target: '/libs/sample', flags: 1 }] });
  for (const f of ['E:\\SampleLib\\x\\y.dll', 'e:\\samplelib', 'E:\\SampleLib2\\x']) {
    const c = cmap(f), j = mapper2.map(f);
    assert.equal(c.out, j, `extra mount mismatch: ${f} (C=${c.out} JS=${j})`);
  }
  // 既定表の件数一致 (C pathreg_mount_count ↔ JS defaultMounts)
  {
    const p = mod._malloc(16); mod.stringToUTF8('E:\\SampleLib', p, 16);
    assert.equal(mod._pathreg_remove_mount(p), 0);
    mod._free(p);
  }
  assert.equal(mod._pathreg_mount_count(), defaultMounts().length, '既定マウント表の件数一致');
  mod._free(inBuf); mod._free(outBuf);
  ok(`C: C↔JS 写像クロスチェック (${fixtures.length} fixtures + 追加マウント + 表件数)`);
}

console.log(`E2E PASS: ${pass} groups`);
